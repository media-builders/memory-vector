import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { resolveConfig, runPythonScript } from "./python-bridge.js";
import { execFileSync } from "child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCRIPTS_DIR = path.resolve(__dirname, "..", "scripts");

let watchers = [];
let watcherTimer = null;
let pendingPaths = new Set();

/**
 * Check if a changed file is relevant for memory indexing.
 * Relevant: agent MEMORY.md, memory/*.md, .git repo changes inside the configured memory root.
 */
function resolveRootPath(workspaceRoot, rootPath) {
  return path.isAbsolute(rootPath) ? rootPath : path.join(workspaceRoot, rootPath);
}

function isInside(parentPath, childPath) {
  const rel = path.relative(parentPath, childPath);
  return rel && !rel.startsWith("..") && !path.isAbsolute(rel);
}

function configuredMemoryPaths(config) {
  return (config.memoryPaths || []).map((value) => resolveRootPath(config.workspaceRoot, value));
}

function isRelevantConfiguredPath(filePath, targets) {
  if (!filePath.endsWith(".md")) return false;
  const resolved = path.resolve(filePath);
  return targets.some((target) => {
    if (!fs.existsSync(target)) return false;
    const targetResolved = path.resolve(target);
    const stat = fs.statSync(targetResolved);
    if (stat.isFile()) return resolved === targetResolved;
    return isInside(targetResolved, resolved);
  });
}

function isRelevantPath(filePath, config, memoryRootPath, ignoreAgents = ["brain", "headquarters", "knowledge"]) {
  const targets = configuredMemoryPaths(config);
  if (targets.length > 0) {
    return isRelevantConfiguredPath(filePath, targets);
  }

  const rel = path.relative(memoryRootPath, filePath);

  // Must be under the configured memory root.
  if (!rel || rel.startsWith("..")) return false;

  const parts = rel.split(path.sep);
  const agentDir = parts[0];

  // Skip ignored agents
  if (ignoreAgents.includes(agentDir)) return false;

  // Skip venvs, node_modules, __pycache__
  if (parts.some((p) => [".venv", "node_modules", "__pycache__", ".git"].includes(p) && p !== ".git")) {
    // .git itself is relevant, but contents inside .git are not
    if (parts.includes(".git") && parts.indexOf(".git") < parts.length - 1) return false;
  }

  const fileName = path.basename(filePath);

  // MEMORY.md in agent root
  if (fileName === "MEMORY.md" && path.dirname(filePath) === path.join(memoryRootPath, agentDir)) {
    return true;
  }

  // memory/*.md files
  if (parts.length >= 3 && parts[1] === "memory" && fileName.endsWith(".md")) {
    return true;
  }

  // .git changes (but not internals)
  if (fileName === ".git" && path.basename(path.dirname(filePath)) === agentDir) {
    return true;
  }

  return false;
}

/**
 * Run the ingest pipeline: chunk inventory → embeddings → LanceDB.
 */
async function runRefresh(config) {
  const workspaceRoot = config.workspaceRoot;

  try {
    // Step 1: chunk inventory (uses system python, stdlib only)
    execFileSync(config.pythonPath || "python3", [
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
  } catch (e) {
    // ingest_memory may warn but still work
  }

  // Step 2: embeddings update (uses venv python with sentence-transformers)
  try {
    await runPythonScript("update_vector_memory.py", [config.workspaceRoot, config.indexPath], config);
  } catch (e) {
    // fallback
  }
}

/**
 * Start watching the configured memory root for memory file changes.
 * Debounces changes and runs ingest on relevant files.
 */
export async function startWatcher(pluginConfig = {}) {
  if (watchers.length > 0) return;

  const config = resolveConfig(pluginConfig);
  const memoryRootPath = resolveRootPath(config.workspaceRoot, config.memoryRoot);
  const configuredRoots = configuredMemoryPaths(config);
  const watchRoots = configuredRoots.length > 0
    ? configuredRoots.map((target) => {
        if (!fs.existsSync(target)) return null;
        const stat = fs.statSync(target);
        return stat.isFile() ? path.dirname(target) : target;
      }).filter(Boolean)
    : [memoryRootPath];

  const uniqueWatchRoots = [...new Set(watchRoots.map((root) => path.resolve(root)))].filter((root) => fs.existsSync(root));
  if (uniqueWatchRoots.length === 0) return;

  const debounceMs = (pluginConfig.watchDebounceSeconds || 2) * 1000;

  for (const watchRoot of uniqueWatchRoots) {
    const watcher = fs.watch(watchRoot, { recursive: true }, (eventType, filename) => {
      if (!filename) return;

      const filePath = path.join(watchRoot, filename);

      if (!isRelevantPath(filePath, config, memoryRootPath)) return;

      pendingPaths.add(filePath);

      if (watcherTimer) clearTimeout(watcherTimer);
      watcherTimer = setTimeout(async () => {
        const paths = [...pendingPaths];
        pendingPaths.clear();
        await runRefresh(config);
      }, debounceMs);
    });

    watcher.on("error", () => {
      // fs.watch may error on some platforms; silently recover
    });

    watchers.push(watcher);
  }

  // Run initial refresh
  await runRefresh(config);
}

/**
 * Stop the file watcher.
 */
export function stopWatcher() {
  if (watcherTimer) {
    clearTimeout(watcherTimer);
    watcherTimer = null;
  }
  for (const watcher of watchers) {
    watcher.close();
  }
  watchers = [];
  pendingPaths.clear();
}
