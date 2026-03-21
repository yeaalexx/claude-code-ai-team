"""
RAG-based Semantic Memory — v4.0

Provides semantic search over learnings using ChromaDB with lightweight
embeddings. Falls back gracefully to no-op if chromadb is not installed.

ChromaDB storage: ~/.claude-mcp-servers/multi-ai-collab/memory/chroma/
Collection: "learnings" with metadata: category, project, source, confidence, timestamp
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Module state — set by initialize()
_collection: Any = None
_client: Any = None
_available: bool = False
_initialized: bool = False


def _is_available() -> bool:
    """Check if RAG memory is available (chromadb installed + initialized)."""
    return _available and _initialized


def initialize(base_dir: Path) -> None:
    """Initialize ChromaDB persistent client.

    Args:
        base_dir: Server base directory (e.g. ~/.claude-mcp-servers/multi-ai-collab/)
    """
    global _collection, _client, _available, _initialized

    if _initialized:
        return

    try:
        import chromadb

        chroma_path = base_dir / "memory" / "chroma"
        chroma_path.mkdir(parents=True, exist_ok=True)

        _client = chromadb.PersistentClient(path=str(chroma_path))
        _collection = _client.get_or_create_collection(
            name="learnings",
            metadata={"hnsw:space": "cosine"},
        )
        _available = True
        _initialized = True
        logger.info("RAG memory initialized with ChromaDB at %s", chroma_path)

    except ImportError:
        logger.warning("chromadb not installed — RAG semantic search disabled. Install with: pip install chromadb")
        _available = False
        _initialized = True
    except Exception as e:
        logger.warning("Failed to initialize ChromaDB: %s", e)
        _available = False
        _initialized = True


def _learning_id(content: str, category: str) -> str:
    """Generate a deterministic document ID for deduplication."""
    raw = f"{category}:{content.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def migrate_from_json(json_path: Path) -> int:
    """Import existing grok-memory.json learnings into ChromaDB.

    Idempotent — safe to run multiple times. Skips learnings already present
    by using deterministic IDs based on content hash.

    Args:
        json_path: Path to grok-memory.json

    Returns:
        Number of new learnings imported.
    """
    if not _is_available():
        return 0

    if not json_path.exists():
        return 0

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s for migration: %s", json_path, e)
        return 0

    learnings = data.get("learnings", [])
    if not learnings:
        return 0

    # Get existing IDs to skip duplicates
    existing_ids = set()
    try:
        existing = _collection.get()
        existing_ids = set(existing["ids"]) if existing and existing.get("ids") else set()
    except Exception:
        pass

    # Batch add — ChromaDB is most efficient with batches
    new_ids: list[str] = []
    new_docs: list[str] = []
    new_metadatas: list[dict[str, Any]] = []

    for entry in learnings:
        content = entry.get("content", "").strip()
        if not content:
            continue

        category = entry.get("category", "uncategorized")
        doc_id = _learning_id(content, category)

        if doc_id in existing_ids:
            continue

        new_ids.append(doc_id)
        new_docs.append(content)
        new_metadatas.append(
            {
                "category": category,
                "project": entry.get("project", ""),
                "source": entry.get("source", "unknown"),
                "confidence": float(entry.get("confidence", 0.5)),
                "timestamp": entry.get("timestamp", ""),
                "original_id": entry.get("id", ""),
            }
        )

    if not new_ids:
        return 0

    # ChromaDB has a batch size limit; chunk if needed
    batch_size = 500
    imported = 0
    for i in range(0, len(new_ids), batch_size):
        chunk_ids = new_ids[i : i + batch_size]
        chunk_docs = new_docs[i : i + batch_size]
        chunk_meta = new_metadatas[i : i + batch_size]
        try:
            _collection.add(
                ids=chunk_ids,
                documents=chunk_docs,
                metadatas=chunk_meta,
            )
            imported += len(chunk_ids)
        except Exception as e:
            logger.warning("Failed to add batch to ChromaDB: %s", e)

    logger.info("Migrated %d learnings from JSON to ChromaDB", imported)
    return imported


def add_learning(
    source: str,
    category: str,
    content: str,
    project: str = "",
    confidence: float = 0.8,
) -> bool:
    """Add a learning to ChromaDB.

    Args:
        source: Who created the learning (grok, claude, collaboration)
        category: Learning category
        content: The learning content
        project: Project name
        confidence: Confidence score 0.0-1.0

    Returns:
        True if added, False if skipped (duplicate or unavailable)
    """
    if not _is_available():
        return False

    content = content.strip()
    if not content:
        return False

    doc_id = _learning_id(content, category)

    try:
        # Upsert to handle duplicates gracefully
        _collection.upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[
                {
                    "category": category,
                    "project": project,
                    "source": source,
                    "confidence": confidence,
                    "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                }
            ],
        )
        return True
    except Exception as e:
        logger.warning("Failed to add learning to ChromaDB: %s", e)
        return False


def query_relevant(
    query_text: str,
    n_results: int = 20,
    category_filter: str | None = None,
    project_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic search for relevant learnings.

    Args:
        query_text: Natural language query to search for
        n_results: Maximum number of results to return
        category_filter: If set, only return learnings in this category
        project_filter: If set, only return learnings for this project (+ general)

    Returns:
        List of dicts with keys: content, category, project, source, confidence,
        timestamp, distance (lower = more relevant)
    """
    if not _is_available() or not query_text.strip():
        return []

    try:
        where_filter = _build_where_filter(category_filter, project_filter)

        kwargs: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": n_results,
        }
        if where_filter:
            kwargs["where"] = where_filter

        results = _collection.query(**kwargs)

        if not results or not results.get("documents") or not results["documents"][0]:
            return []

        output = []
        docs = results["documents"][0]
        metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

        for doc, meta, dist in zip(docs, metadatas, distances, strict=False):
            output.append(
                {
                    "content": doc,
                    "category": meta.get("category", "uncategorized"),
                    "project": meta.get("project", ""),
                    "source": meta.get("source", "unknown"),
                    "confidence": meta.get("confidence", 0.5),
                    "timestamp": meta.get("timestamp", ""),
                    "distance": dist,
                }
            )

        return output

    except Exception as e:
        logger.warning("RAG query failed: %s", e)
        return []


def _build_where_filter(
    category_filter: str | None,
    project_filter: str | None,
) -> dict[str, Any] | None:
    """Build a ChromaDB where filter from category and project constraints."""
    conditions: list[dict[str, Any]] = []

    if category_filter:
        conditions.append({"category": {"$eq": category_filter}})

    if project_filter:
        # Include both project-specific and general (empty project) learnings
        conditions.append(
            {
                "$or": [
                    {"project": {"$eq": project_filter}},
                    {"project": {"$eq": ""}},
                ]
            }
        )

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def get_stats() -> dict[str, Any]:
    """Get RAG collection statistics.

    Returns:
        Dict with count, categories breakdown, and availability status.
    """
    if not _is_available():
        return {
            "available": False,
            "count": 0,
            "categories": {},
        }

    try:
        count = _collection.count()

        # Get category breakdown by fetching all metadata
        categories: dict[str, int] = {}
        if count > 0:
            all_data = _collection.get(include=["metadatas"])
            if all_data and all_data.get("metadatas"):
                for meta in all_data["metadatas"]:
                    cat = meta.get("category", "uncategorized") if meta else "uncategorized"
                    categories[cat] = categories.get(cat, 0) + 1

        return {
            "available": True,
            "count": count,
            "categories": categories,
        }
    except Exception as e:
        logger.warning("Failed to get RAG stats: %s", e)
        return {
            "available": True,
            "count": -1,
            "categories": {},
            "error": str(e),
        }
