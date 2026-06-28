# AI Installation Instructions

Use this runbook when an OpenClaw agent is asked to install the `memory-vector` plugin for a user. This is an operator workflow. Do not blindly copy local paths from examples; discover the user's actual OpenClaw home, workspace, plugin path, and memory folders first.

## Goal

Install and configure the `memory-vector` plugin so OpenClaw can:

- load the plugin on Gateway startup
- ingest the user's memory markdown files
- build the Python virtual environment and vector index
- keep the plugin available through the managed Gateway service
- optionally start the plugin watcher
- pass a smoke test before reporting success

## Critical Rules

- Always inspect the user's filesystem before editing config.
- Always confirm discovered memory paths with the user before writing `openclaw.json`.
- If no memory paths are found, ask the user for exact memory file or folder paths.
- Preserve the user's existing `openclaw.json` entries; append or merge plugin config instead of replacing unrelated config.
- Back up `openclaw.json` before editing it.
- Use real absolute paths in `openclaw.json`; do not leave placeholders like `<WORKSPACE_ROOT>` in live config.
- Do not create a separate OS service for this plugin unless the user explicitly requests a custom external watcher. The normal startup service is the OpenClaw Gateway service. The plugin watcher runs inside the Gateway/plugin runtime.

## Expected Plugin Inputs

The plugin supports these path settings:

- `workspaceRoot`: absolute path to the user's OpenClaw workspace
- `memoryRoot`: broad folder containing memory workspaces, relative to `workspaceRoot` or absolute
- `memoryPaths`: exact files or folders to ingest; use this when the user does not have a broad memory root
- `indexPath`: where generated vector files and LanceDB data are written
- `plugins.load.paths[]`: absolute path to the installed plugin directory

Git commit history is collected from repositories discovered under `workspaceRoot`. `memoryPaths` controls markdown memory ingestion only; it should not be used to narrow git discovery.

Prefer `memoryPaths` for public installs because users may only have a specific folder such as:

```text
<WORKSPACE_ROOT>/agents/<AGENT_OR_WORKSPACE>/memory
```

## Phase 1 - Identify The Environment

Determine these values:

```text
OPENCLAW_HOME
WORKSPACE_ROOT
PLUGIN_DIR
OPENCLAW_CONFIG
```

Default assumptions:

```text
OPENCLAW_HOME=~/.openclaw
WORKSPACE_ROOT=$OPENCLAW_HOME/workspace
PLUGIN_DIR=$WORKSPACE_ROOT/plugins/memory-vector
OPENCLAW_CONFIG=$OPENCLAW_HOME/openclaw.json
```

Use shell checks to verify:

```bash
test -f "$OPENCLAW_CONFIG"
test -d "$WORKSPACE_ROOT"
test -d "$PLUGIN_DIR"
test -f "$PLUGIN_DIR/openclaw.plugin.json"
```

If the plugin is in a source checkout rather than `workspace/plugins/memory-vector`, either install/copy/link it into the user's plugin area or set `plugins.load.paths[]` to the actual absolute plugin directory.

## Phase 2 - Spider Crawl For Memory Files

Search the workspace for likely memory files and folders. Use `find` or `rg --files`, whichever is available.

Recommended crawl:

```bash
cd "$WORKSPACE_ROOT"

find . \
  -path '*/node_modules/*' -prune -o \
  -path '*/.venv/*' -prune -o \
  -path '*/__pycache__/*' -prune -o \
  -path '*/.git/*' -prune -o \
  \( -name 'MEMORY.md' -o -path '*/memory/*.md' \) \
  -type f -print
```

Also identify exact candidate memory folders:

```bash
find "$WORKSPACE_ROOT" \
  -path '*/node_modules/*' -prune -o \
  -path '*/.venv/*' -prune -o \
  -path '*/__pycache__/*' -prune -o \
  -path '*/.git/*' -prune -o \
  -type d -name memory -print
```

Prefer folders that contain real markdown memory files:

```bash
find "$WORKSPACE_ROOT" -type d -name memory -print | while read -r dir; do
  count="$(find "$dir" -maxdepth 1 -type f -name '*.md' | wc -l | tr -d ' ')"
  if [ "$count" != "0" ]; then
    printf '%s\t%s markdown files\n' "$dir" "$count"
  fi
done
```

Also check for agent-style roots:

```bash
find "$WORKSPACE_ROOT" -maxdepth 4 -type f -name AGENTS.md -print
```

Use the crawl results to build a candidate list:

- exact memory folders, e.g. `$WORKSPACE_ROOT/agents/<AGENT_OR_WORKSPACE>/memory`
- durable memory files, e.g. `$WORKSPACE_ROOT/agents/<AGENT_OR_WORKSPACE>/MEMORY.md`
- broad roots only when appropriate, e.g. `$WORKSPACE_ROOT/agents`

## Phase 3 - Confirm Paths With The User

Before editing config, show the user a concise list:

```text
I found these memory candidates:

1. <path> (<N> markdown files)
2. <path> (<N> markdown files)
3. <path> (MEMORY.md)

I plan to set memoryPaths to:
- <path>
- <path>

Please confirm, remove any wrong paths, or provide additional paths to include.
```

If no paths were found, ask:

```text
I could not find memory folders automatically. Please send the exact file or folder paths you want indexed, for example:
<WORKSPACE_ROOT>/agents/<AGENT_OR_WORKSPACE>/memory
<WORKSPACE_ROOT>/agents/<AGENT_OR_WORKSPACE>/MEMORY.md
```

Only continue after the user confirms or supplies override paths.

## Phase 4 - Install Dependencies

From the plugin directory:

```bash
cd "$PLUGIN_DIR"
npm install
python3 -m venv scripts/.venv
scripts/.venv/bin/pip install --upgrade pip
scripts/.venv/bin/pip install -r scripts/requirements.txt
```

If `scripts/requirements.txt` is missing or incomplete:

```bash
scripts/.venv/bin/pip install sentence-transformers lancedb pyarrow numpy
```

Verify basic syntax:

```bash
npm run verify
python3 -m py_compile scripts/ingest_memory.py scripts/update_vector_memory.py scripts/search_memory.py
```

## Phase 5 - Update openclaw.json

Back up the config:

```bash
cp "$OPENCLAW_CONFIG" "$OPENCLAW_CONFIG.bak.$(date +%Y%m%d-%H%M%S)"
```

Merge the plugin config into `plugins.entries.memory-vector`. Preserve all existing unrelated config.

Recommended config shape:

```json
{
  "plugins": {
    "entries": {
      "memory-vector": {
        "enabled": true,
        "config": {
          "workspaceRoot": "<WORKSPACE_ROOT_ABSOLUTE_PATH>",
          "memoryRoot": ".",
          "memoryPaths": [
            "<CONFIRMED_MEMORY_PATH_1>",
            "<CONFIRMED_MEMORY_PATH_2>"
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
        "<PLUGIN_DIR_ABSOLUTE_PATH>"
      ]
    }
  }
}
```

Important merge behavior:

- If `plugins.entries` already exists, add or update only `memory-vector`.
- If `plugins.allow` exists, append `"memory-vector"` if missing.
- If `plugins.allow` does not exist, do not create a restrictive allowlist unless needed by the user's config style.
- If `plugins.load.paths` exists, append the absolute plugin directory if missing.
- If the confirmed paths are exact folders or files, put them in `memoryPaths`.
- Make sure `workspaceRoot` is the workspace whose git repositories should be included in date summaries.
- Use forward slashes in JSON paths on Windows, or escape backslashes.

Validate:

```bash
openclaw config validate
```

If validation fails, restore the backup or fix only the invalid plugin config.

## Phase 6 - Install Startup Services

Install or refresh the managed OpenClaw Gateway startup service:

```bash
openclaw gateway install
openclaw gateway restart
openclaw gateway status --deep
```

This is the startup service that matters. The `memory-vector` plugin loads inside the Gateway process.

Watcher handling:

- The plugin exposes `memory_vector_watch`.
- The config includes `watchEnabled`, but do not assume unattended watcher startup unless verified on that plugin version.
- For reliable installation, first prove the plugin loads and ingest works.
- Then start the watcher through the OpenClaw tool surface if the user wants live auto-indexing.

Do not invent a separate systemd/launchd/schtasks service for the watcher unless the user explicitly requests custom external supervision.

## Phase 7 - Build The Index

Preferred smoke path: use the plugin tools from an OpenClaw agent session:

```text
memory_vector_ingest
memory_vector_status
memory_vector_search {"query":"memory", "maxResults":5}
```

If plugin tools are not directly callable from the current shell, use the Python scripts as a fallback smoke test:

```bash
cd "$PLUGIN_DIR"

python3 scripts/ingest_memory.py \
  "$WORKSPACE_ROOT" \
  "plugins/memory-vector/vector" \
  "." \
  '["<CONFIRMED_MEMORY_PATH_1>","<CONFIRMED_MEMORY_PATH_2>"]'

scripts/.venv/bin/python scripts/update_vector_memory.py \
  "$WORKSPACE_ROOT" \
  "plugins/memory-vector/vector"
```

Then verify generated output exists:

```bash
test -s "$WORKSPACE_ROOT/plugins/memory-vector/vector/chunks.jsonl"
test -d "$WORKSPACE_ROOT/plugins/memory-vector/vector/lancedb"
```

## Phase 8 - Plugin Runtime Smoke Test

Run:

```bash
openclaw plugins inspect memory-vector --runtime --json
openclaw gateway status --deep
```

Confirm:

- plugin status is loaded
- `memory_vector_search` appears
- `memory_vector_ingest` appears
- `memory_vector_watch` appears
- `memory_vector_status` appears
- diagnostics are empty or non-blocking

If the tool surface is available, run:

```text
memory_vector_status
memory_vector_search {"query":"recent memory", "maxResults":5}
```

For watcher smoke:

```text
memory_vector_watch {"action":"start"}
memory_vector_watch {"action":"status"}
```

If the status action only returns generic guidance, report that the watcher tool is present but this plugin build does not expose deep watcher state.

## Phase 9 - Final Report To User

Report:

- plugin directory used
- config file edited
- confirmed memory paths installed
- whether the Gateway service was installed/restarted
- whether index build passed
- whether plugin runtime inspect passed
- whether watcher was started or left manual
- any warnings from `openclaw config validate` or `gateway status --deep`

Example final summary:

```text
Installed memory-vector.

Configured memoryPaths:
- ...

Gateway startup service: installed and restarted.
Index: built successfully.
Tools: memory_vector_search, memory_vector_ingest, memory_vector_watch, memory_vector_status loaded.
Watcher: started manually / left disabled pending confirmation.
Smoke test: passed.
```

## Failure Handling

If no memory files are found:

- Stop before editing config.
- Ask the user for exact memory folder/file paths.

If Python dependency install fails:

- Report the package error.
- Do not edit `openclaw.json` unless dependencies are recoverable or the user explicitly wants config staged.

If Gateway restart fails:

- Run `openclaw gateway status --deep`.
- Report the exact failing service or config error.
- Do not claim installation success.

If ingest finds zero chunks:

- Recheck `memoryPaths`.
- Confirm markdown files exist under the configured paths.
- Ask the user whether to add more paths.
