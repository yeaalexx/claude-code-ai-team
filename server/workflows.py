"""
Validation Workflows — v5.0

State machine workflows for file change validation.
Inspired by LangGraph but implemented as lightweight Python without the dependency.

Each workflow takes a file change event and runs it through a pipeline:
  PENDING -> LOADING_CONTRACTS -> VALIDATING -> REVIEWING -> DECIDED -> COMPLETE

The workflow uses callback-based AI integration so it stays decoupled from
the MCP server. The `ai_caller` and `contracts_loader` are injected at
invocation time, making workflows independently testable.
"""

import asyncio
import enum
import logging
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowState(enum.Enum):
    """States in the validation workflow."""

    PENDING = "PENDING"
    LOADING_CONTRACTS = "LOADING_CONTRACTS"
    VALIDATING = "VALIDATING"
    REVIEWING = "REVIEWING"
    DECIDED = "DECIDED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class Decision(enum.Enum):
    """Outcome decisions from the validation workflow."""

    CLEAN = "clean"  # No issues found
    NOTIFY = "notify"  # Minor issues — inform the developer
    PROPOSE_FIX = "propose_fix"  # Contract violation — suggest a fix
    ESCALATE = "escalate"  # Compliance risk — needs human attention


# Type aliases for the callback signatures
AiCaller = Callable[[str, str], Awaitable[str]]
"""async (system_prompt, user_message) -> ai_response"""

ContractsLoader = Callable[[str, str | None], Awaitable[dict[str, str]]]
"""async (contracts_path, service_name) -> {"filename": "content", ...}"""


@dataclass
class ValidationResult:
    """The outcome of a single validation workflow run."""

    workflow_id: str
    event: dict[str, Any]
    state: WorkflowState
    decision: Decision | None = None
    validation_response: str = ""
    review_response: str = ""
    issues: list[dict[str, str]] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    error: str = ""
    contracts_loaded: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "event": self.event,
            "state": self.state.value,
            "decision": self.decision.value if self.decision else None,
            "validation_response": self.validation_response,
            "review_response": self.review_response,
            "issues": self.issues,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "contracts_loaded": self.contracts_loaded,
        }


class ValidationWorkflow:
    """A single validation workflow instance.

    Runs a file change event through a sequence of states, using injected
    callbacks for AI calls and contract loading.

    The workflow is async. Each state transition is a coroutine that can
    be awaited. The caller drives execution via `run()`.
    """

    def __init__(
        self,
        event: dict[str, Any],
        ai_caller: AiCaller,
        contracts_loader: ContractsLoader,
        contracts_path: str = "contracts/",
    ) -> None:
        self.workflow_id = str(uuid.uuid4())[:12]
        self.event = event
        self.ai_caller = ai_caller
        self.contracts_loader = contracts_loader
        self.contracts_path = contracts_path

        self.result = ValidationResult(
            workflow_id=self.workflow_id,
            event=event,
            state=WorkflowState.PENDING,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        # Internal state for passing data between steps
        self._contracts: dict[str, str] = {}

    async def run(self) -> ValidationResult:
        """Execute the full workflow pipeline.

        Returns the final ValidationResult. If any step fails, the workflow
        moves to FAILED state with an error message.
        """
        steps: list[tuple[WorkflowState, Callable[[], Awaitable[None]]]] = [
            (WorkflowState.LOADING_CONTRACTS, self._load_contracts),
            (WorkflowState.VALIDATING, self._validate),
            (WorkflowState.REVIEWING, self._review),
            (WorkflowState.DECIDED, self._decide),
        ]

        for target_state, step_fn in steps:
            self.result.state = target_state
            try:
                await step_fn()
            except Exception as e:
                logger.exception(
                    "Workflow %s failed in state %s",
                    self.workflow_id,
                    target_state.value,
                )
                self.result.state = WorkflowState.FAILED
                self.result.error = f"{target_state.value}: {e}"
                self.result.completed_at = datetime.now(timezone.utc).isoformat()
                return self.result

        self.result.state = WorkflowState.COMPLETE
        self.result.completed_at = datetime.now(timezone.utc).isoformat()
        return self.result

    async def _load_contracts(self) -> None:
        """Load relevant contract files for the changed service."""
        service = self.event.get("service")
        self._contracts = await self.contracts_loader(self.contracts_path, service)
        self.result.contracts_loaded = list(self._contracts.keys())
        logger.debug(
            "Workflow %s: loaded %d contract files for service=%s",
            self.workflow_id,
            len(self._contracts),
            service,
        )

    async def _validate(self) -> None:
        """Call AI to validate the file change against loaded contracts."""
        if not self._contracts:
            # No contracts to validate against — auto-clean
            self.result.validation_response = "No contracts found — skipping validation."
            return

        contracts_text = "\n\n".join(f"### {name}\n{content}" for name, content in self._contracts.items())

        system_prompt = (
            "You are a contract validation assistant. Given a file change event and "
            "the project's integration contracts, check whether the change could "
            "violate any contract. Be specific about which contract clause is at risk.\n\n"
            "Respond with a JSON object:\n"
            '{"issues": [{"severity": "info|warning|violation|compliance_risk", '
            '"description": "...", "contract_ref": "..."}], '
            '"summary": "one-line summary"}\n\n'
            "If no issues are found, return an empty issues array."
        )

        user_message = (
            f"## File Change Event\n"
            f"- Path: {self.event.get('path', 'unknown')}\n"
            f"- Event type: {self.event.get('event_type', 'unknown')}\n"
            f"- Service: {self.event.get('service', 'N/A')}\n"
            f"- Timestamp: {self.event.get('timestamp', 'unknown')}\n\n"
            f"## Relevant Contracts\n{contracts_text}"
        )

        response = await self.ai_caller(system_prompt, user_message)
        self.result.validation_response = response

        # Try to parse structured issues from the response
        self.result.issues = _extract_issues(response)

    async def _review(self) -> None:
        """If validation found issues, request a second-opinion review.

        Only runs if there are warning-level or higher issues from validation.
        """
        significant_issues = [
            i for i in self.result.issues if i.get("severity") in ("warning", "violation", "compliance_risk")
        ]

        if not significant_issues:
            self.result.review_response = "No significant issues — review skipped."
            return

        system_prompt = (
            "You are a second-opinion reviewer for integration contract compliance. "
            "Another AI found potential issues with a file change. Review the issues "
            "and determine which are genuine concerns vs false positives.\n\n"
            "Respond with a JSON object:\n"
            '{"confirmed": [{"description": "...", "severity": "..."}], '
            '"dismissed": [{"description": "...", "reason": "..."}], '
            '"summary": "one-line verdict"}'
        )

        issues_text = "\n".join(
            f"- [{i.get('severity', '?')}] {i.get('description', '?')} (ref: {i.get('contract_ref', 'N/A')})"
            for i in significant_issues
        )

        user_message = (
            f"## Original Change\n"
            f"- Path: {self.event.get('path', 'unknown')}\n"
            f"- Service: {self.event.get('service', 'N/A')}\n\n"
            f"## Issues Found by Validator\n{issues_text}"
        )

        response = await self.ai_caller(system_prompt, user_message)
        self.result.review_response = response

    async def _decide(self) -> None:
        """Determine the final action based on validation + review results."""
        if not self.result.issues:
            self.result.decision = Decision.CLEAN
            return

        # Check for compliance risks
        severities = {i.get("severity", "info") for i in self.result.issues}

        if "compliance_risk" in severities:
            self.result.decision = Decision.ESCALATE
        elif "violation" in severities:
            self.result.decision = Decision.PROPOSE_FIX
        elif "warning" in severities:
            self.result.decision = Decision.NOTIFY
        else:
            self.result.decision = Decision.CLEAN


def _extract_issues(response: str) -> list[dict[str, str]]:
    """Try to extract structured issues from an AI response.

    Attempts JSON parsing first. Falls back to empty list if the response
    is not valid JSON (the caller should still read the raw text).
    """
    import json

    # Try to find a JSON block in the response
    text = response.strip()

    # Look for ```json ... ``` fenced blocks
    if "```json" in text:
        start = text.index("```json") + len("```json")
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "issues" in data:
            return list(data["issues"])
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    return []


class WorkflowManager:
    """Tracks all validation workflows (pending and completed).

    Thread-safe. Maintains an in-memory bounded history of workflow results.
    """

    def __init__(self, max_results: int = 100) -> None:
        self._results: deque[ValidationResult] = deque(maxlen=max_results)
        self._active: dict[str, ValidationWorkflow] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self,
        event: dict[str, Any],
        ai_caller: AiCaller,
        contracts_loader: ContractsLoader,
        contracts_path: str = "contracts/",
    ) -> ValidationResult:
        """Create and run a validation workflow for a file change event.

        Args:
            event: File change event dict (path, event_type, timestamp, service).
            ai_caller: Async callback for AI calls.
            contracts_loader: Async callback to load contract files.
            contracts_path: Relative path to the contracts directory.

        Returns:
            The completed ValidationResult.
        """
        workflow = ValidationWorkflow(
            event=event,
            ai_caller=ai_caller,
            contracts_loader=contracts_loader,
            contracts_path=contracts_path,
        )

        async with self._lock:
            self._active[workflow.workflow_id] = workflow

        try:
            result = await workflow.run()
        finally:
            async with self._lock:
                self._active.pop(workflow.workflow_id, None)
                self._results.append(result)

        return result

    async def get_active(self) -> list[dict[str, Any]]:
        """Return summaries of currently running workflows."""
        async with self._lock:
            return [
                {
                    "workflow_id": w.workflow_id,
                    "event": w.event,
                    "state": w.result.state.value,
                    "started_at": w.result.started_at,
                }
                for w in self._active.values()
            ]

    def get_completed(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent completed workflow results.

        Args:
            limit: Maximum number of results (most recent first).
        """
        results = list(self._results)
        results.reverse()
        return [r.to_dict() for r in results[:limit]]

    def get_summary(self) -> dict[str, Any]:
        """Return aggregate statistics about all tracked workflows."""
        completed = list(self._results)
        decisions: dict[str, int] = {}
        states: dict[str, int] = {}

        for r in completed:
            state_key = r.state.value
            states[state_key] = states.get(state_key, 0) + 1
            if r.decision is not None:
                dec_key = r.decision.value
                decisions[dec_key] = decisions.get(dec_key, 0) + 1

        return {
            "total_completed": len(completed),
            "active_count": len(self._active),
            "decisions": decisions,
            "states": states,
        }


async def run_validation(
    event: dict[str, Any],
    ai_caller: AiCaller,
    contracts_loader: ContractsLoader,
    contracts_path: str = "contracts/",
) -> ValidationResult:
    """Run a single validation workflow for a file change event.

    This is the main entry point. It creates a workflow, runs it, and returns
    the result. For tracking multiple workflows, use WorkflowManager instead.

    Args:
        event: File change event with keys: path, event_type, timestamp, service.
        ai_caller: async (system_prompt, user_message) -> response_text
        contracts_loader: async (contracts_path, service_name) -> {filename: content}
        contracts_path: Relative path to contracts directory.

    Returns:
        Completed ValidationResult.
    """
    workflow = ValidationWorkflow(
        event=event,
        ai_caller=ai_caller,
        contracts_loader=contracts_loader,
        contracts_path=contracts_path,
    )
    return await workflow.run()
