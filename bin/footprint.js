#!/usr/bin/env node
const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const root = path.join(__dirname, "..");
const script = path.join(root, "footprint.py");
const win = process.platform === "win32";
const venvPy = win
  ? path.join(root, ".venv", "Scripts", "python.exe")
  : path.join(root, ".venv", "bin", "python");
const args = process.argv.slice(2);

if (args.length === 0) {
  require("./banner");
}

if (!fs.existsSync(venvPy)) {
  console.log("first run — setting up (venv + model backend)…");
  const s = spawnSync(win ? "python" : "python3", [script, "setup"], { stdio: "inherit" });
  if (s.status) process.exit(s.status);
}

const r = spawnSync(venvPy, [script, ...(args.length ? args : ["status"])], {
  stdio: "inherit",
});
process.exit(r.status === null ? 1 : r.status);
