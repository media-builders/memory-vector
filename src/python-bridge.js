import { spawn } from "child_process";
import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const SCRIPTS_DIR = path.join(PLUGIN_ROOT, "scripts");

/**
 * Resolve the Python binary from plugin config, falling back to "python3".
 */
function resolvePython(config = {}) {
  return config.pythonPath || "python3";
}

/**
 * Ensure the Python venv exists. Creates it if missing.
 */
function ensureVenv(config = {}) {
  const venvPath = config.venvPath
    ? path.resolve(config.venvPath)
    : path.join(SCRIPTS_DIR, ".venv");
  const pythonBin = path.join(venvPath, "bin", "python");

  if (!fs.existsSync(pythonBin)) {
    return { venvPath, pythonBin, ready: false, missing: "venv not found" };
  }

  return { venvPath, pythonBin, ready: true };
}

function normalizeMemoryPaths(value) {
  if (Array.isArray(value)) {
    return value.filter((item) => typeof item === "string" && item.trim());
  }
  if (typeof value === "string" && value.trim()) {
    return [value];
  }
  return [];
}

/**
 * Run a Python script and return stdout as parsed JSON.
 */
export function runPythonScript(scriptName, args = [], config = {}) {
  const python = resolvePython(config);
  const { pythonBin, ready, missing } = ensureVenv(config);

  if (!ready) {
    return Promise.reject(new Error(`Python venv not available: ${missing}`));
  }

  const scriptPath = path.join(SCRIPTS_DIR, scriptName);
  if (!fs.existsSync(scriptPath)) {
    return Promise.reject(new Error(`Script not found: ${scriptPath}`));
  }

  return new Promise((resolve, reject) => {
    const proc = spawn(pythonBin, [scriptPath, ...args], {
      cwd: SCRIPTS_DIR,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        MEMORY_WORKSPACE_ROOT: config.workspaceRoot || "",
        MEMORY_ROOT: config.memoryRoot || "",
        MEMORY_INDEX_PATH: config.indexPath || "",
        MEMORY_PATHS: JSON.stringify(config.memoryPaths || []),
      },
      timeout: 120000, // 2 minute timeout
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    proc.on("close", (code) => {
      if (code === 0) {
        try {
          const result = JSON.parse(stdout.trim());
          resolve(result);
        } catch {
          resolve({ raw: stdout.trim() });
        }
      } else {
        reject(
          new Error(
            `Python script ${scriptName} exited with code ${code}: ${stderr || stdout}`
          )
        );
      }
    });

    proc.on("error", (err) => {
      reject(new Error(`Failed to spawn ${scriptName}: ${err.message}`));
    });
  });
}

/**
 * Read plugin config with defaults.
 */
export function resolveConfig(pluginConfig = {}) {
  const home = process.env.HOME || process.env.USERPROFILE || "/root";
  return {
    workspaceRoot: pluginConfig.workspaceRoot || path.join(home, ".openclaw/workspace"),
    memoryRoot: pluginConfig.memoryRoot || ".",
    memoryPaths: normalizeMemoryPaths(pluginConfig.memoryPaths),
    indexPath: pluginConfig.indexPath || "plugins/memory-vector/vector",
    embeddingModel: pluginConfig.embeddingModel || "all-MiniLM-L6-v2",
    maxSearchResults: pluginConfig.maxSearchResults || 20,
    pythonPath: pluginConfig.pythonPath || "python3",
    venvPath: pluginConfig.venvPath || path.join(SCRIPTS_DIR, ".venv"),
  };
}
