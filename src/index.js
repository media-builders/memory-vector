import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { runPythonScript, resolveConfig } from "./python-bridge.js";
import { startWatcher, stopWatcher } from "./watcher.js";
import path from "path";
import fs from "fs";
import { execFileSync } from "child_process";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCRIPTS_DIR = path.resolve(__dirname, "..", "scripts");

function resolveConfiguredPath(workspaceRoot, value) {
  return path.isAbsolute(value) ? value : path.join(workspaceRoot, value);
}

function textResult(text) {
  return { content: [{ type: "text", text }] };
}
function errorResult(message) {
  return { content: [{ type: "text", text: `Error: ${message}` }] };
}

export default definePluginEntry({
  id: "memory-vector",
  name: "Memory Vector",
  description: "Semantic search over configured memory files using LanceDB vector embeddings.",

  register(api) {
    api.registerTool({
      name: "memory_vector_search",
      description: "Search indexed memory with a natural language query.",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string", description: "Natural language search query. Leave empty when using sourceFilter to get all content from a date." },
          maxResults: { type: "number", description: "Max results, default 20, max 50" },
          agentFilter: { type: "string", description: "Limit to specific agent workspace" },
          type: { type: "string", enum: ["memory", "daily", "git", "all"], description: "Content type filter" },
          sourceFilter: { type: "string", description: "Exact partial match on source file path (e.g. 2026-05-15)" },
        },
        required: [],
      },
      async execute(_toolId, params) {
        try {
          const config = resolveConfig(api.pluginConfig || {});
          const query = params.query || ".";
          const maxResults = Math.min(params.maxResults || 20, 50);
          const agentFilter = params.agentFilter || "";
          const type = params.type || "all";
          const sourceFilter = params.sourceFilter || "";

          if (!query.trim() || query === ".") {
            // sourceFilter is the real driver — bypass semantic search
          }

          const result = await runPythonScript(
            "search_memory.py",
            [query, config.workspaceRoot, config.indexPath, String(maxResults), agentFilter, type, sourceFilter],
            config
          );

          if (result.error) {
            return errorResult(`${result.error}: ${result.message || ""}`);
          }

          const lines = [
            `Memory search: "${query}"`,
            `Found ${result.totalHits} results (showing ${result.results?.length || 0})`,
            "",
            ...(result.results || []).map(
              (r, i) =>
                `${i + 1}. [${r.agent || "unknown"}] ${r.type || "memory"} | score: ${r.score}\n   Source: ${r.source}\n   ${r.snippet || ""}`
            ),
          ];

          if ((result.results || []).length === 0) {
            lines.push("No results found. Try a different query or run memory_vector_ingest.");
          }

          return textResult(lines.join("\n"));
        } catch (err) {
          return errorResult(err.message);
        }
      },
    });

    api.registerTool({
      name: "memory_vector_ingest",
      description: "Refresh the vector memory index from configured files, folders, and repositories.",
      parameters: {
        type: "object",
        properties: {
          agentFilter: { type: "string", description: "Limit to specific agent workspace" },
          fullRebuild: { type: "boolean", description: "Rebuild index from scratch" },
        },
      },
      async execute(_toolId, params) {
        try {
          const config = resolveConfig(api.pluginConfig || {});
          const workspaceRoot = config.workspaceRoot;

          try {
            execFileSync(config.pythonPath, [
              path.join(SCRIPTS_DIR, "ingest_memory.py"),
              workspaceRoot,
              config.indexPath,
              config.memoryRoot,
              JSON.stringify(config.memoryPaths || []),
            ], {
              timeout: 60000,
              encoding: "utf8",
              stdio: "pipe",
            });
          } catch {
            // Non-zero exit ok on first run
          }

          const result = await runPythonScript(
            "update_vector_memory.py",
            [config.workspaceRoot, config.indexPath],
            config
          );

          if (result.error) {
            return errorResult(`${result.error}: ${result.message || ""}`);
          }

          return textResult(
            `Vector memory ingest complete.\n` +
              `Chunks indexed: ${result.chunks || "unknown"}\n` +
              `Index path: ${resolveConfiguredPath(workspaceRoot, config.indexPath)}`
          );
        } catch (err) {
          return errorResult(err.message);
        }
      },
    });

    api.registerTool({
      name: "memory_vector_watch",
      description: "Start, stop, or check the background file watcher for auto-indexing.",
      parameters: {
        type: "object",
        properties: {
          action: { type: "string", enum: ["start", "stop", "status"] },
        },
        required: ["action"],
      },
      async execute(_toolId, params) {
        try {
          const action = params.action || "status";
          if (action === "start") {
            const config = resolveConfig(api.pluginConfig || {});
            await startWatcher(config);
            return textResult("Memory watcher started. Auto-indexing on file changes.");
          }
          if (action === "stop") {
            stopWatcher();
            return textResult("Memory watcher stopped.");
          }
          return textResult("Use start/stop to control the watcher. Check memory_vector_status for index stats.");
        } catch (err) {
          return errorResult(err.message);
        }
      },
    });

    api.registerTool({
      name: "memory_vector_status",
      description: "Report current state of the vector memory index.",
      parameters: { type: "object", properties: {} },
      async execute(_toolId, _params) {
        try {
          const config = resolveConfig(api.pluginConfig || {});
          const indexPath = path.join(resolveConfiguredPath(config.workspaceRoot, config.indexPath), "lancedb", "memory_chunks.lance");

          if (!fs.existsSync(indexPath)) {
            return textResult(`Vector memory index not found at: ${indexPath}\nRun memory_vector_ingest to create it.`);
          }

          const stat = fs.statSync(indexPath);
          return textResult(
            `Vector Memory Index\nIndex: ${indexPath}\nSize: ${(stat.size / 1024 / 1024).toFixed(1)} MB\nLast modified: ${stat.mtime.toISOString()}\nStatus: Active`
          );
        } catch (err) {
          return errorResult(err.message);
        }
      },
    });
  },
});
