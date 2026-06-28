# Memory Vector Plugin Installation Guide

This guide explains how to install the `memory-vector` OpenClaw plugin, register its tools, configure `openclaw.json`, and make sure OpenClaw loads it every time the Gateway starts.

## Path Placeholders

This guide uses placeholders so it can be shared across machines:

- `<OPENCLAW_HOME>`: the user's OpenClaw home directory, usually `~/.openclaw`
- `<WORKSPACE_ROOT>`: the OpenClaw workspace root, usually `<OPENCLAW_HOME>/workspace`
- `<PLUGIN_DIR>`: the installed plugin directory, usually `<WORKSPACE_ROOT>/plugins/memory-vector`
- `<SOURCE_DIR>`: an optional source checkout, if different from the installed plugin directory
- `<MEMORY_ROOT>`: a broad folder containing memory workspaces, relative to `<WORKSPACE_ROOT>` or absolute
- `<MEMORY_PATH>`: an exact memory file or folder to ingest

When editing `openclaw.json`, replace placeholders with real absolute paths for that machine. For most local installs, `<OPENCLAW_HOME>` is the user's home-directory `.openclaw` folder and `<WORKSPACE_ROOT>` is its `workspace` subdirectory.

## What This Plugin Registers

The plugin is a native OpenClaw plugin. Its manifest is `openclaw.plugin.json`, and its runtime entry point is `src/index.js`.

It declares and registers these agent tools:

- `memory_vector_search`: semantic search over indexed memory
- `memory_vector_ingest`: scan memory files and rebuild or refresh the vector index
- `memory_vector_watch`: start or stop the background file watcher
- `memory_vector_status`: report the current index path and health

The tools are declared in `openclaw.plugin.json` under `contracts.tools` and are registered at runtime with `api.registerTool(...)` in `src/index.js`.

## What Gets Ingested

Yes, the plugin ingests memory files. `memory_vector_ingest` scans the configured memory root and creates chunk records before generating embeddings.

By default, the broad source memory root is the workspace root:

```text
<WORKSPACE_ROOT>
```

Within that root, the plugin ingests:

- `<MEMORY_ROOT>/<AGENT_OR_WORKSPACE>/MEMORY.md`
- `<MEMORY_ROOT>/<AGENT_OR_WORKSPACE>/memory/*.md`
- Git commit history from repositories found under `<MEMORY_ROOT>`

A workspace folder is considered ingestible when it is a directory under `<MEMORY_ROOT>` and contains `AGENTS.md`.

If a user does not have a broader memory root, set `memoryPaths` instead. When `memoryPaths` is set, the plugin ingests those exact files or folders instead of scanning `memoryRoot`.

Examples:

```json
{
  "memoryPaths": [
    "<WORKSPACE_ROOT>/agents/<AGENT_OR_WORKSPACE>/memory"
  ]
}
```

```json
{
  "memoryPaths": [
    "<WORKSPACE_ROOT>/agents/<AGENT_OR_WORKSPACE>/MEMORY.md",
    "<WORKSPACE_ROOT>/agents/<AGENT_OR_WORKSPACE>/memory"
  ]
}
```

For JSON on Windows, either use forward slashes or escape backslashes:

```json
{
  "memoryPaths": [
    "C:/Users/<USER>/.openclaw/workspace/agents/<AGENT_OR_WORKSPACE>/memory"
  ]
}
```

The plugin writes generated chunks, embeddings, and LanceDB data to:

```text
<WORKSPACE_ROOT>/<indexPath>
```

With the recommended config, that resolves to:

```text
<WORKSPACE_ROOT>/plugins/memory-vector/vector
```

## Active Install Location

OpenClaw should load the plugin from the operational plugin directory:

```text
<PLUGIN_DIR>
```

The project/source copy may live elsewhere, for example:

```text
<SOURCE_DIR>
```

For the running Gateway, the important path is the one listed in `plugins.load.paths` in `~/.openclaw/openclaw.json`.

## Prerequisites

Install these on the Gateway host:

- OpenClaw CLI and Gateway
- Node.js
- Python 3 with `venv`
- Enough disk space for the Python virtual environment and embedding model

From the plugin root:

```bash
cd "<PLUGIN_DIR>"
npm install
python3 -m venv scripts/.venv
scripts/.venv/bin/pip install -r scripts/requirements.txt
```

If `scripts/requirements.txt` is unavailable or incomplete, install the runtime Python dependencies directly:

```bash
scripts/.venv/bin/pip install sentence-transformers lancedb pyarrow numpy
```

## Register the Plugin in OpenClaw

OpenClaw discovers local plugins from `plugins.load.paths`. Add the plugin directory there, enable the plugin under `plugins.entries`, and include it in `plugins.allow` if your config uses an allowlist.

Use this shape in `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "memory-vector": {
        "enabled": true,
        "config": {
          "workspaceRoot": "<WORKSPACE_ROOT>",
          "memoryRoot": ".",
          "memoryPaths": [
            "<MEMORY_PATH>"
          ],
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

This is a template. Use real absolute paths in `openclaw.json`; do not leave `<WORKSPACE_ROOT>` or `<PLUGIN_DIR>` in the live config.

If your existing `plugins.allow` already contains other plugins, append `"memory-vector"` instead of replacing the list.

If your existing `plugins.load.paths` already contains other local plugin paths, append the memory-vector path instead of replacing the list.

## Config Fields

| Field | Required | Recommended value | Purpose |
|---|---:|---|---|
| `workspaceRoot` | Yes | `<WORKSPACE_ROOT>` | Root path used to resolve relative plugin paths. |
| `memoryRoot` | No | `.` | Broad folder containing memory workspaces. Relative values resolve under `workspaceRoot`; absolute values are allowed. Prefer `memoryPaths` for exact public installs. |
| `memoryPaths` | No | `[]` | Exact memory files or folders to ingest. When set, this takes precedence over `memoryRoot`. |
| `indexPath` | Yes | `plugins/memory-vector/vector` | Vector index path relative to `workspaceRoot`. |
| `embeddingModel` | No | `all-MiniLM-L6-v2` | Sentence Transformers model used for embeddings. |
| `maxSearchResults` | No | `20` | Default maximum search results. Tool calls may still pass their own limit. |
| `pythonPath` | No | `python3` | System Python used for setup/helper calls. Runtime scripts use `scripts/.venv/bin/python`. |
| `venvPath` | No | omit unless custom | Optional absolute path to a Python virtualenv. Defaults to `scripts/.venv` in the plugin directory. |
| `watchEnabled` | No | `false` for manual operation, `true` only after verifying startup watcher behavior | Intended to auto-start watching when the plugin activates. |
| `watchDebounceSeconds` | No | `2` | Debounce window before refresh after memory file changes. |

## Startup Services

Register the OpenClaw Gateway as the managed startup service. Do not register a separate systemd service for this plugin unless you intentionally want an external indexing process.

On Linux or WSL2:

```bash
openclaw gateway install
openclaw gateway restart
openclaw gateway status --deep
```

On macOS, the same command installs or refreshes the LaunchAgent:

```bash
openclaw gateway install
openclaw gateway restart
```

On native Windows, OpenClaw uses a Scheduled Task or login startup fallback:

```powershell
openclaw gateway install
openclaw gateway restart
```

The important service is the Gateway service because native plugins load inside the Gateway process. When the Gateway starts, OpenClaw reads `openclaw.json`, discovers the plugin from `plugins.load.paths`, checks `plugins.entries.memory-vector.enabled`, validates the manifest, and loads `src/index.js`.

## Update Folder Paths

There are five folder path settings that matter:

- `plugins.load.paths[]`: where OpenClaw loads the plugin code from
- `workspaceRoot`: the base OpenClaw workspace path
- `memoryRoot`: where the plugin scans for agent folders and memory files
- `memoryPaths`: exact memory files or folders to ingest
- `indexPath`: where generated vector data is written and searched

For exact memory paths, use:

```json
{
  "workspaceRoot": "<WORKSPACE_ROOT>",
  "memoryRoot": ".",
  "memoryPaths": [
    "<MEMORY_PATH>"
  ],
  "indexPath": "plugins/memory-vector/vector"
}
```

If the user's agent folders live somewhere else inside the workspace, change `memoryRoot`:

```json
{
  "workspaceRoot": "<WORKSPACE_ROOT>",
  "memoryRoot": "agents",
  "memoryPaths": [],
  "indexPath": "plugins/memory-vector/vector"
}
```

If the user only has one exact memory folder, use `memoryPaths`:

```json
{
  "workspaceRoot": "<WORKSPACE_ROOT>",
  "memoryPaths": [
    "<WORKSPACE_ROOT>/agents/<AGENT_OR_WORKSPACE>/memory"
  ],
  "indexPath": "plugins/memory-vector/vector"
}
```

If the memory folder is outside the OpenClaw workspace, use an absolute `memoryRoot` or absolute `memoryPaths`:

```json
{
  "workspaceRoot": "<WORKSPACE_ROOT>",
  "memoryPaths": [
    "<ABSOLUTE_PATH_TO_MEMORY_FOLDER>"
  ],
  "indexPath": "plugins/memory-vector/vector"
}
```

If `memoryPaths` points at a folder, all markdown files under that folder are ingested. If it points at a single `.md` file, only that file is ingested.

If the vector index should live somewhere else, change `indexPath`. Relative paths resolve under `workspaceRoot`; absolute paths are also supported by the Python scripts and search tool.

After changing any path:

```bash
openclaw gateway restart
```

Then rebuild the index:

```text
memory_vector_ingest
```

## Make It Load on Every OpenClaw Launch

To make the plugin tools available every time OpenClaw launches:

1. Keep `"memory-vector"` in `plugins.allow` when an allowlist is configured.
2. Keep `plugins.entries.memory-vector.enabled` set to `true`.
3. Keep the installed plugin directory in `plugins.load.paths`.
4. Keep the plugin manifest at `<PLUGIN_DIR>/openclaw.plugin.json`.
5. Install the Gateway service with `openclaw gateway install`.
6. Restart the Gateway after config or plugin code changes.

The plugin manifest also has:

```json
{
  "activation": {
    "onStartup": true
  }
}
```

That tells OpenClaw this plugin should be part of startup activation instead of waiting for some later capability path.

## Watcher Behavior

The plugin exposes the watcher through:

```text
memory_vector_watch {"action":"start"}
memory_vector_watch {"action":"stop"}
memory_vector_watch {"action":"status"}
```

The config schema includes `watchEnabled`, described as starting the file watcher on plugin activation. Verify this behavior in the running Gateway before relying on it for unattended indexing. In the current source, tool registration is automatic, but the watcher is visibly controlled through the `memory_vector_watch` tool.

Operational recommendation:

- Keep `watchEnabled: false` if you only want manual or on-demand indexing through `memory_vector_ingest`.
- Use `memory_vector_watch {"action":"start"}` after Gateway startup when you need live auto-indexing.
- Set `watchEnabled: true` only after confirming the running plugin build starts the watcher during plugin activation.

No separate OpenClaw startup service is required for tool availability. The Gateway service is the startup service.

## Build the Index

After the Gateway loads the plugin, run:

```text
memory_vector_ingest
```

This scans memory files under the configured workspace, generates embeddings, and writes LanceDB output under:

```text
<WORKSPACE_ROOT>/plugins/memory-vector/vector
```

Check status with:

```text
memory_vector_status
```

Search with:

```text
memory_vector_search {"query":"what happened with the watcher dashboard","maxResults":10}
```

## Validation

Run these checks after installation or config edits:

```bash
cd "<PLUGIN_DIR>"
npm run verify
openclaw plugins list
openclaw plugins inspect memory-vector --runtime --json
openclaw gateway status --deep
```

Restart the Gateway after changing `openclaw.json`, plugin code, or `plugins.load.paths`:

```bash
openclaw gateway restart
```

## Troubleshooting

If the tools do not appear:

- Confirm `plugins.entries.memory-vector.enabled` is `true`.
- Confirm `"memory-vector"` is present in `plugins.allow` if `plugins.allow` exists.
- Confirm the plugin directory is present in `plugins.load.paths`.
- Restart the Gateway after config changes.
- Run `openclaw plugins inspect memory-vector --runtime --json`.

If search says the index is missing:

- Run `memory_vector_ingest`.
- Confirm `indexPath` points to `plugins/memory-vector/vector`.
- Confirm the LanceDB directory exists under `vector/lancedb`.

If Python fails:

- Confirm `scripts/.venv/bin/python` exists.
- Reinstall dependencies with `scripts/.venv/bin/pip install -r scripts/requirements.txt`.
- Confirm the Gateway service user can read the plugin directory and vector directory.

If watcher behavior is required on startup:

- First verify manual watcher startup with `memory_vector_watch {"action":"start"}`.
- Then verify whether `watchEnabled: true` starts the watcher after a Gateway restart.
- If it does not, the plugin needs a startup hook or registration-time call to `startWatcher(...)`; until then, use manual watcher start or on-demand `memory_vector_ingest`.
