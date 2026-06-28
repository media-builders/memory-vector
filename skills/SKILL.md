---
name: recall
description: Recall and summarize indexed memory by date or topic using the memory-vector plugin tools. Use when an agent needs to answer questions like what happened today, what happened on a given date, what a role or project worked on, or when asked to recall prior activity, notes, or memory with a date filter.
---

# Recall

Use the `memory_vector_search` plugin tool to retrieve indexed memory from the LanceDB vector index, then summarize it.

This skill must be portable across OpenClaw workspaces. Do not assume the user has any specific top-level folder or agent layout.

## What This Skill Does

This skill helps an agent:

- retrieve indexed memory and git activity by date
- retrieve semantically relevant memory by topic
- check index health and refresh the index when stale
- summarize retrieved evidence into a useful answer
- answer questions like:
  - what happened today?
  - what happened on 2026-04-21?
  - what did engineering work on today?
  - recall what we discussed about a topic

## Config Awareness

The plugin indexes whichever paths were configured during installation:

- `memoryPaths`: exact memory files or folders to ingest; preferred for portable installs
- `memoryRoot`: a broad folder to scan when the user has a consistent workspace tree
- `workspaceRoot`: the base path used to resolve relative paths
- `indexPath`: where the vector index is stored

When answering recall questions, treat the retrieved result paths and metadata as the source of truth. Do not hard-code path assumptions.

## Ground Rules

- Daily memory may come from files named `memory/YYYY-MM-DD.md`, but the exact parent path depends on the user's configured `memoryPaths` or `memoryRoot`.
- Durable memory may come from files named `MEMORY.md`, but the exact parent path depends on the user's configuration.
- Git history is indexed from git repositories discovered under `workspaceRoot`, independent of exact `memoryPaths`.
- Use the plugin tools first, then summarize with the LLM.
- Do not invent activity that is not present in retrieved results.
- Distinguish memory notes from commit evidence when it matters.
- If today's memory is mostly setup or initialization, say so plainly.
- If retrieved results show an unexpected folder layout, follow the evidence instead of assuming a standard OpenClaw workspace tree.

## Plugin Tools

All commands use the `memory_vector_*` plugin tools. No shell scripts are needed during normal recall.

### Date-Scoped Retrieval

Use this when the user asks what happened on a specific date:

```text
memory_vector_search sourceFilter="YYYY-MM-DD"
```

Set `maxResults` higher for busy days, such as `50` to `100`. Leave `query` empty to get all chunks from that date. Date-scoped retrieval matches both dated memory files and git commits whose indexed `date` or timestamp matches the filter. Add `agentFilter` only when the retrieved metadata uses agent names and the user wants one role, project, or workspace.

### Semantic Search

Use this when the user asks about a topic:

```text
memory_vector_search query="natural language question"
```

Use `agentFilter`, `type`, and `maxResults` to narrow results when the metadata supports it. A good `maxResults` default is `15` to `20` for topic queries.

### Index Refresh

Refresh before a recall if the index might be stale:

```text
memory_vector_ingest
```

Use `fullRebuild: true` only when the index is corrupted, after significant path/config changes, or after the user explicitly asks for a full rebuild.

### Index Health

Check index state with:

```text
memory_vector_status
```

Use this to inspect last ingest time, chunk count, and configured paths when recall results look incomplete.

## Workflow

### 1. If The User Asks For Recall By Date

Examples:

- "what happened today?"
- "recall 2026-04-21"
- "what happened yesterday?"

Action:

- Resolve relative dates to an exact `YYYY-MM-DD` date.
- Run `memory_vector_search` with `sourceFilter` set to that date.
- Use an empty or missing query to get all indexed memory notes and git commits from that date.
- Set `maxResults` appropriately, such as `50` for busy days or `20` for quiet days.
- Summarize the retrieved results into the standard report format.
- If the user asks you to save the report, write it to a user-approved path or a configured report/journal folder if one is documented for that workspace.

### 2. If The User Asks For Recall By Topic

Examples:

- "recall what we said about onboarding"
- "what have we discussed about deployment reliability?"
- "what did this project decide about memory search?"

Action:

- Run `memory_vector_search` with a descriptive `query`.
- Set `maxResults` to `10` to `20`.
- Optionally add `agentFilter` or `type` filters when relevant.
- Summarize the retrieved results.

### 3. If Retrieval May Be Stale

Refresh first:

```text
memory_vector_ingest
```

This updates the LanceDB index by scanning the configured memory files/folders and git repositories under `workspaceRoot`.

## Output Guidance

Default to a daily report format when the user asks for recall by date, especially for prompts like "what happened yesterday", "what happened today", or anything that will feed a scheduled summary.

Preferred structure:

- **Daily Recall Report**
- **Date**
- **Executive Summary**
- **Progress**
- **By Source / Role / Project**
- **Operational Themes**
- **Notable Evidence**
- **Blockers / Risks**
- **Bottom Line**

Formatting rules:

- Summarize what happened at a high level first.
- Then summarize by role, project, or source when retrieved metadata supports it.
- If a category has no distinct activity surfaced, say so plainly.
- Merge memory notes and git evidence into one coherent report.
- Do not dump raw retrieval output unless the user asks.
- Keep a clean report tone suitable for future scheduled delivery.
- Call out important commits, project shifts, infrastructure changes, and risks when they materially shaped the day.
- Distinguish substantive work from setup/admin cleanup when relevant.
- Include concise source pointers from retrieved paths or commit IDs when they help verification.

For topic-based recall instead of date-based recall, use a lighter summary format when a full report would feel unnatural.

## Persistence Rule

Do not assume a report should be saved under any particular folder.

When this skill generates a date-based daily report:

- Save it only if the user asks, a scheduler/runbook requires persistence, or a workspace-specific report path is documented.
- Prefer an existing configured report or journal folder when one is available.
- If no report path is known, ask the user for the destination before writing.
- Use the resolved report date in the filename, not words like `today` or `yesterday`.

If the user asked for a lightweight topic recall instead of a full daily report, saving is optional unless they explicitly ask for it.

## Important Limitation

This skill retrieves and summarizes indexed memory plus indexed git commit history.

If memory notes happened outside the configured memory paths, or code work happened outside git repositories under `workspaceRoot`, recall quality will be limited by that missing input. In that case, explain the likely path/config gap and suggest updating `memoryPaths`, `memoryRoot`, or `workspaceRoot`.
