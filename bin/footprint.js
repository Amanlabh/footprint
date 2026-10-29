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

// context/collect/status are stdlib-only: system python, no venv, no model download.
// Only the local-model commands need the venv + backend (setup = local mode opt-in).
const sysPy = win ? "python" : "python3";
const needsModel = ["train", "eval", "serve", "install"].includes(args[0]);
if (needsModel && !fs.existsSync(venvPy)) {
  console.log("local model mode — setting up (venv + model backend, one-time)…");
  const s = spawnSync(sysPy, [script, "setup"], { stdio: "inherit" });
  if (s.status) process.exit(s.status);
}

const py = fs.existsSync(venvPy) ? venvPy : sysPy;
const r = spawnSync(py, [script, ...(args.length ? args : ["status"])], {
  stdio: "inherit",
});
process.exit(r.status === null ? 1 : r.status);
