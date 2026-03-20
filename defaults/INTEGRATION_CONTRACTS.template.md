<!-- AUTO-CREATED by Claude Code on first session in multi-service projects.
     This file defines the integration contracts between services in your project.
     Claude will populate this with project-specific data during auto-bootstrap.
     Do not delete sections — fill them in as services are built.
     Keep this file in the project root alongside CLAUDE.md. -->

# Integration Contracts

> Cross-service rules that every AI agent (and human developer) must follow.
> This is the single source of truth for how services communicate.

## Service Dependency Matrix

| From | To | Method | Required Headers | Key Rules |
|------|----|--------|-----------------|-----------|
| <!-- service-a --> | <!-- service-b --> | <!-- REST/gRPC/Kafka --> | <!-- e.g., Authorization, X-Tenant-ID --> | <!-- e.g., must emit audit event --> |

<!-- Add one row per integration point. Include both synchronous (REST/gRPC)
     and asynchronous (Kafka/event) dependencies. -->

## Universal Rules

<!-- These rules apply to ALL inter-service communication. Number them for easy reference. -->

1. **Tenant ID Propagation** — <!-- How tenant context flows between services (header, JWT claim, query param). -->
2. **Auth Header Forwarding** — <!-- How Authorization headers are passed between services. -->
3. **Event Emission** — <!-- Which mutations must emit events, to which topic, in what format. -->
4. **Error Response Format** — <!-- Standard error envelope all services must return. -->
5. **ID Format** — <!-- UUID version, format, generation rules. -->

## Anti-Patterns (Learned from Incidents)

<!-- Document integration mistakes that caused bugs, outages, or data issues.
     Format each entry as follows: -->

<!--
### AP-001: Short descriptive title
- **Sprint/Date:** when it happened
- **What went wrong:** description of the failure
- **Root cause:** why the anti-pattern exists
- **Correct pattern:** what to do instead
-->
