# Memory Vector

`memory-vector` is an OpenClaw plugin that adds semantic search over local memory markdown files using Sentence Transformers and LanceDB.

## Tools

The plugin registers four OpenClaw tools:

- `memory_vector_ingest`: discovers memory files, chunks them, generates embeddings, and rebuilds the LanceDB table
- `memory_vector_search`: searches indexed memory with a natural-language query
- `memory_vector_watch`: starts or stops background indexing for changed memory files
- `memory_vector_status`: reports the current vector index state

## What It Ingests

The plugin can ingest either a broad OpenClaw-style memory root or exact files/folders.

Default root-style layout:

```text
<WORKSPACE_ROOT>/company/<agent>/MEMORY.md
<WORKSPACE_ROOT>/company/<agent>/memory/*.md
```

Exact path layout:

```json
{
  "memoryPaths": [
    "<WORKSPACE_ROOT>/company/engineering-head/memory",
    "<WORKSPACE_ROOT>/company/engineering-head/MEMORY.md"
  ]
}
```

`memoryPaths` is recommended for portable installs because users may not have a full `company` tree.

## Documentation

- [Installation guide](docs/INSTALLATION.md)
- [AI installation instructions](docs/AI_Installation_Instructions.md)

## Quick Install Shape

Add the plugin to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "memory-vector": {
        "enabled": true,
        "config": {
          "workspaceRoot": "<WORKSPACE_ROOT>",
          "memoryRoot": "company",
          "memoryPaths": [],
          "indexPath": "plugins/memory-vector/vector",
          "embeddingModel": "all-MiniLM-L6-v2",
          "maxSearchResults": 20,
          "pythonPath": "python3",
          "watchEnabled": false,
          "watchDebounceSeconds": 2
        }
      }
    },
    "allow": [
      "memory-vector"
    ],
    "load": {
      "paths": [
        "<PLUGIN_DIR>"
      ]
    }
  }
}
```

Then install dependencies from the plugin directory:

```bash
npm install
python3 -m venv scripts/.venv
scripts/.venv/bin/pip install -r scripts/requirements.txt
```

Restart the Gateway after config changes:

```bash
openclaw gateway restart
```

Build the index with:

```text
memory_vector_ingest
```
