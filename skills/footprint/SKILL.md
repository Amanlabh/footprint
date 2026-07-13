---
name: footprint
description: Local SLM that learns from Claude Code transcripts ("footprint") and replays the project's working style. Trigger on /footprint, "take footprint", "train footprint", "footprint status", "footprint run <task>".
---

# Footprint

Footprint collects this machine's Claude Code session transcripts, fine-tunes a
small local model on them (MLX LoRA on Apple Silicon, torch+PEFT elsewhere),
and serves it as an OpenAI-compatible API for OpenCode/Cursor/Codex.
Code layout: `footprint.py` (entry shim) -> `footprint_core/` (cli, config,
transcripts, service, backends/{mlx,torch}_backend.py).

Repo: `/Users/aman/Developer/footprint`. Python: `/Users/aman/Developer/footprint/.venv/bin/python`
(if `.venv` missing, run `setup` first with system `python3`).

## Commands

Map the user's `/footprint <arg>` to one Bash call:

| Invocation | Run |
|---|---|
| `/footprint` or `/footprint status` | `.venv/bin/python footprint.py status` |
| `/footprint setup` | `python3 footprint.py setup` |
| `/footprint trace` | `.venv/bin/python footprint.py trace` (arm BEFORE chatting; only sessions after this become training data) |
| `/footprint collect` | `.venv/bin/python footprint.py collect <current project dir>` |
| `/footprint collect all` | `.venv/bin/python footprint.py collect --all-projects-nonexistent-dir` (falls back to all projects) |
| `/footprint train` | `.venv/bin/python footprint.py train` (long; run in background) |
| `/footprint install` | `.venv/bin/python footprint.py install` (launchd auto-server + OpenCode `/footprint` command — user never runs serve) |
| `/footprint serve` | `.venv/bin/python footprint.py serve` (manual fallback only; install makes this unnecessary) |

Always run commands from `/Users/aman/Developer/footprint`.

## Flow for a fresh user

1. `setup` — venv + mlx-lm + skill symlink.
2. `trace` — arm tracing FIRST, before chatting with Claude. Writes `~/.claude/footprint-trace`; collect then only uses sessions newer than the marker (delete marker to use all history).
3. Chat with Claude Code normally — sessions land in `~/.claude/projects` automatically.
4. `collect` — parses `~/.claude/projects/<project>/*.jsonl` into `data/train.jsonl` + `data/valid.jsonl` (chat format, tool calls encoded as `<tool name="...">{args}</tool>`).
5. `train` — LoRA on `mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit` (override with `FOOTPRINT_MODEL`, iterations with `FOOTPRINT_ITERS`, default 300). Downloads ~1 GB first time. Run in background, report loss when done.
6. `install` — the user never runs the server. launchd (`com.footprint.serve`, KeepAlive) keeps the OpenAI-compatible API at `http://127.0.0.1:8399/v1` running across reboots/crashes. Also installs into OpenCode: provider `footprint` + `/footprint <task>` command (`~/.config/opencode/command/footprint.md`) so typing `/footprint` there makes OpenCode work like Claude.
   Other tools point at the always-on server:
   - **Cursor**: Settings → Models → OpenAI base URL `http://127.0.0.1:8399/v1`, any API key, add model `footprint`.
   - **Codex CLI**: set a custom provider with that base URL in `~/.codex/config.toml`.

Report command output tersely. If mlx-lm import fails, rerun `setup`.
