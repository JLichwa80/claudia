#!/usr/bin/env node
/**
 * install-local.js  —  Claudia Local Model Config setup
 *
 * Installs the Python dependency (Gradio) for launch.py.
 * Usage:
 *   node bin/install-local.js         # from cloned repo
 *   npx get-claudia-local             # if published to npm
 */

import { spawnSync } from "child_process";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const LAUNCH_PY = resolve(__dirname, "..", "launch.py");

const hr = "─".repeat(52);
console.log(`\n${hr}`);
console.log("  Claudia  ×  Local Model Config  —  Setup");
console.log(`${hr}\n`);

// ── Find Python ────────────────────────────────────────────────────────────────
function findPython() {
  for (const cmd of ["python3", "python"]) {
    const r = spawnSync(cmd, ["--version"], { encoding: "utf8" });
    if (r.status === 0) {
      const ver = (r.stdout || r.stderr).trim();
      console.log(`  ✓  Found ${ver}  (${cmd})`);
      return cmd;
    }
  }
  return null;
}

const python = findPython();
if (!python) {
  console.error("  ✗  Python 3 not found. Install Python 3.10+ and try again.");
  console.error("     https://www.python.org/downloads/\n");
  process.exit(1);
}

// ── Install Gradio ─────────────────────────────────────────────────────────────
console.log("\n  Installing Gradio…");
const pip = spawnSync(
  python,
  ["-m", "pip", "install", "--upgrade", "gradio>=4.0"],
  { stdio: "inherit" }
);
if (pip.status !== 0) {
  console.error("\n  ✗  pip install failed. Try: pip install gradio");
  process.exit(1);
}

// ── Done ───────────────────────────────────────────────────────────────────────
console.log(`\n${hr}`);
console.log("  ✓  Setup complete!\n");
console.log("  Run the configuration dashboard:");
console.log(`\n      ${python} ${LAUNCH_PY}\n`);
console.log("  Or from the claudia directory:");
console.log("\n      python launch.py\n");
console.log(
  "  Prerequisite: Claudia workspace created with  npx get-claudia\n"
);
console.log(hr + "\n");
