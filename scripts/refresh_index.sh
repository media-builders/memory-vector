#!/usr/bin/env bash
set -euo pipefail

WS="${1:-$HOME/.openclaw/workspace}"
INDEX_PATH="${2:-plugins/memory-vector/vector}"
MEMORY_ROOT="${3:-.}"
MEMORY_PATHS="${4:-[]}"
PLUGIN="$WS/plugins/memory-vector"

python3 "$PLUGIN/scripts/ingest_memory.py" "$WS" "$INDEX_PATH" "$MEMORY_ROOT" "$MEMORY_PATHS"
"$PLUGIN/scripts/.venv/bin/python" "$PLUGIN/scripts/update_vector_memory.py" "$WS" "$INDEX_PATH"
echo "Memory index refreshed"
