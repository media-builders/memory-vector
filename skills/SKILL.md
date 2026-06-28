\---

name: recall

description: Recall and summarize company memory by date or topic using the memory-vector plugin tools. Use when an agent needs to answer questions like what happened today, what the company did on a given date, what a department worked on, or when asked to recall prior activity, notes, or memory with a date filter.

\---



\# Recall



Use the `memory\_vector\_search` plugin tool to retrieve company activity from the LanceDB vector index, then summarize it.



\## What This Skill Does



This skill helps an agent:

\- retrieve all company memory and git activity by date

\- retrieve semantically relevant memory by topic

\- get index health and refresh the index when stale

\- summarize retrieved evidence into a useful answer

\- answer questions like:

&#x20; - what did the company do today?

&#x20; - what happened on 2026-04-21?

&#x20; - what did engineering work on today?

&#x20; - recall what we discussed about a topic



\## Ground Rules



\- Daily memory comes from `company/<agent>/memory/YYYY-MM-DD.md`.

\- Durable memory comes from `company/<agent>/MEMORY.md`.

\- Git history is also indexed from any git repo found under `company/`.

\- Use the plugin tools first, then summarize with the LLM.

\- Do not invent activity that is not present in retrieved results.

\- Distinguish memory notes from commit evidence when it matters.

\- If today's memory is mostly setup or initialization, say so plainly.



\## Plugin Tools



All commands use the `memory\_vector\_\*` plugin tools. No shell scripts needed.



\### Date-scoped retrieval (all content from a date)



```

memory\_vector\_search sourceFilter="YYYY-MM-DD"

```



Set `maxResults` higher for busy days (e.g., 50-100). Leave `query` empty to get all chunks from that date. Add `agentFilter` to narrow to one department.



\### Semantic search (by topic)



```

memory\_vector\_search query="natural language question"

```



Use `agentFilter`, `type`, and `maxResults` to narrow results. A good `maxResults` default is 15-20 for topic queries.



\### Index refresh



```

memory\_vector\_ingest

```



Run before a recall if the index might be stale. Use `fullRebuild: true` only when the index is corrupted or after significant structural changes.



\### Index health



```

memory\_vector\_status

```



Check before a recall to see last ingest time and chunk count.



\## Workflow



\### 1. If the user asks for recall by date



Examples:

\- "what did the company do today?"

\- "recall 2026-04-21"

\- "what happened yesterday?"



Action:

\- Run `memory\_vector\_search` with `sourceFilter` set to the date

\- Use empty/missing query to get all content from that date

\- Set `maxResults` appropriately (50 for busy days, 20 for quiet days)

\- Summarize the retrieved results into the standard report format

\- If you produce a full daily report, save it to `company/journal/daily-summary-<date>.md`



\### 2. If the user asks for recall by topic



Examples:

\- "recall what we said about scrap business"

\- "what has the company discussed about onboarding?"



Action:

\- Run `memory\_vector\_search` with a descriptive `query`

\- Set `maxResults` to 10-20

\- Optionally add `agentFilter` or `type` filters

\- Summarize the retrieved results



\### 3. If retrieval may be stale



Refresh first:

```

memory\_vector\_ingest

```



This updates the LanceDB index by scanning all agent workspaces for new or changed memory files and git history.



\## Output Guidance



Default to a \*\*daily report format\*\* when the user asks for recall by date, especially for prompts like "what happened yesterday", "what did the company do today", or anything that will feed a scheduled summary.



Preferred structure:

\- \*\*Daily Company Recall Report\*\*

\- \*\*Date\*\*

\- \*\*Executive Summary\*\*

\- \*\*Company-Wide Progress\*\*

\- \*\*By Role\*\*

&#x20; - CEO / Executive

&#x20; - Engineering Head

&#x20; - Design Head

&#x20; - Finance Head

&#x20; - Marketing Head

&#x20; - Product Head

&#x20; - Sales Head

\- \*\*Operational Themes\*\*

\- \*\*Notable Evidence\*\*

\- \*\*Blockers / Risks\*\*

\- \*\*Bottom Line\*\*



Formatting rules:

\- summarize what the company did at a high level first

\- then summarize what each role did, even if the answer is "no distinct activity surfaced"

\- merge memory notes and git evidence into one coherent report

\- do not dump raw retrieval output unless the user asks

\- keep a clean report tone suitable for future cron delivery

\- call out important commits, project shifts, infra changes, and risks when they materially shaped the day

\- distinguish between substantive work and pure setup/admin cleanup when relevant

\- after producing a full daily report, write the exact final markdown to `company/journal/daily-summary-<date>.md` so the report is stored outside the brain workspace



For topic-based recall instead of date-based recall, you can still use a lighter summary format when a full report would feel unnatural.



\## Important Limitation



This skill retrieves and summarizes indexed memory plus indexed git commit history.

If work happened outside agent memory and outside git-tracked repos under `company/`, recall quality will still be limited by that missing input.



\## Persistence Rule



When this skill generates a date-based daily report, the agent should persist the completed report as a markdown file at:

\- `company/journal/daily-summary-YYYY-MM-DD.md`



Use the resolved report date in the filename, not words like `today` or `yesterday`.

If the user asked for a lightweight topic recall instead of a full daily report, saving is optional unless they explicitly ask for it.

