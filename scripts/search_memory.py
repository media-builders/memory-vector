#!/usr/bin/env python3
"""
Memory vector search script invoked by the memory-vector plugin.
Queries the LanceDB index with a natural language query and returns ranked results as JSON.

Usage: python search_memory.py <query> <workspace_root> <index_path> [max_results] [agent_filter] [type_filter] [source_filter]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from sentence_transformers import SentenceTransformer
    import lancedb
except ImportError as e:
    print(json.dumps({"error": f"Missing Python dependency: {e}. Run pip install sentence-transformers lancedb pyarrow in the plugin venv."}))
    sys.exit(1)


def row_matches_source_filter(row: dict, source_filter: str | None) -> bool:
    if not source_filter:
        return True

    needle = source_filter.strip().lower()
    if not needle:
        return True

    fields = (
        "source_file_path",
        "file_path",
        "date",
        "timestamp",
        "authored_at",
        "committed_at",
        "commit_sha",
        "title",
    )
    for field in fields:
        value = row.get(field)
        if value is not None and needle in str(value).lower():
            return True
    return False


def normalized_type(row: dict) -> str:
    file_type = row.get("file_type", "") or ""
    source_type = row.get("source_type", "") or ""

    if file_type == "git_commit" or source_type == "git_commit":
        return "git"
    if file_type == "daily":
        return "daily"
    if file_type in ("durable", "memory") or source_type == "workspace_markdown":
        return "memory"
    return source_type or file_type


def search(query: str, workspace_root: str, index_path: str, max_results: int = 20, agent_filter: str | None = None, type_filter: str = "all", source_filter: str | None = None) -> dict:
    workspace = Path(workspace_root)
    db_path = workspace / index_path / "lancedb"

    if not db_path.exists():
        return {"error": "NO_INDEX", "message": f"LanceDB index not found at {db_path}. Run memory_vector_ingest first."}

    # Load model
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Connect to LanceDB
    db = lancedb.connect(str(db_path))

    table_name = "memory_chunks"
    try:
        table = db.open_table(table_name)
    except Exception:
        return {"error": "NO_INDEX", "message": f"Table '{table_name}' not found. Run memory_vector_ingest first."}

    # If query is empty/placeholder and sourceFilter is set, bypass semantic search
    if (not query or query.strip() in ("*", ".", "all")) and source_filter:
        try:
            # Read all rows from LanceDB and filter by date/source metadata.
            arrow_table = table.to_arrow()
            all_rows = arrow_table.to_pylist()
            results = [r for r in all_rows if row_matches_source_filter(r, source_filter)]
        except Exception as e:
            return {"error": "SEARCH_FAILED", "message": str(e)}
    else:
        # Generate query embedding
        query_embedding = model.encode(query).tolist()

        # Search with wider limit when source filtering
        search_limit = max(max_results * 3, 50) if source_filter else max_results
        try:
            results = table.search(query_embedding).limit(search_limit).to_list()
        except Exception as e:
            return {"error": "SEARCH_FAILED", "message": str(e)}

    # Format results using actual LanceDB schema fields
    hits = []
    for row in results:
        hit = {
            "chunk_id": row.get("chunk_id", ""),
            "source": row.get("source_file_path", row.get("file_path", "")),
            "agent": row.get("agent_id", ""),
            "type": normalized_type(row),
            "rawType": row.get("source_type", row.get("file_type", "")),
            "date": row.get("date", ""),
            "timestamp": row.get("timestamp", ""),
            "commit": row.get("commit_sha", ""),
            "title": row.get("title", ""),
            "snippet": row.get("text", "") or "",
        }
        # Apply filters
        if agent_filter and hit["agent"] != agent_filter:
            continue
        if type_filter != "all" and hit["type"] != type_filter:
            continue
        # Score from LanceDB
        hit["score"] = round(row.get("_distance", 0), 4)
        hits.append(hit)

    # Apply source filter as a date/source metadata filter.
    # When filtering, we searched with a wider limit; now trim to requested max
    if source_filter:
        hits = [h for h in hits if row_matches_source_filter({
            "source_file_path": h.get("source", ""),
            "date": h.get("date", ""),
            "timestamp": h.get("timestamp", ""),
            "commit_sha": h.get("commit", ""),
            "title": h.get("title", ""),
        }, source_filter)]
        hits = hits[:max_results]

    # Get total count
    try:
        total = table.count_rows()
    except Exception:
        total = len(hits)

    return {
        "query": query,
        "results": hits[:max_results],
        "totalHits": len(hits),
        "indexStats": {
            "totalChunks": total,
            "agents": list(set(h["agent"] for h in hits if h.get("agent"))),
        },
    }


def main():
    if len(sys.argv) < 4:
        print(json.dumps({"error": "USAGE", "message": "Usage: search_memory.py <query> <workspace_root> <index_path> [max_results] [agent_filter] [type_filter] [source_filter]"}))
        sys.exit(1)

    query = sys.argv[1] if len(sys.argv) > 1 else "."
    workspace_root = sys.argv[2]
    index_path = sys.argv[3]
    max_results = int(sys.argv[4]) if len(sys.argv) > 4 else 20
    agent_filter = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != "" else None
    type_filter = sys.argv[6] if len(sys.argv) > 6 else "all"

    source_filter = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] != "" else None

    result = search(query, workspace_root, index_path, max_results, agent_filter, type_filter, source_filter)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
