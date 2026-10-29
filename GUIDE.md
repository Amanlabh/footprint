# Footprint Guide

Footprint watches your Claude Code sessions, fine-tunes a small local model (LoRA)
on how *you and Claude* work in your projects, and serves it as an OpenAI-compatible
API. When your Claude quota runs out, OpenCode (or Cursor, or Codex CLI) keeps
working in the same style — fully offline, on your machine.

```
trace → chat with claude → collect → train → install → /footprint in OpenCode
```

## Quick start — continue where you left off

No model download, no training. footprint reads your Claude Code **and** OpenCode
sessions and hands the next session — in either tool — where you left off.

```sh
npm install -g footprint-trace
footprint context install
```

- **Claude Code:** nothing to do — every new session (and `/clear`) starts with
  the previous session's state: goal, files touched, open todos, last error, where it ended.
- **OpenCode:** nothing to do — a plugin gives every new session the same state.
  Pick any model (`/models`, e.g. Big Pickle). In a session that was already open,
  type `/continue` or `/continue <next task>`.
- **Both ways:** switch Claude → OpenCode → Claude freely; the newest session in the
  project (from either tool) is what gets handed over.
- Preview what gets handed over: `footprint context`

## Local model mode (optional)

Everything below trains and serves a small local model on your sessions —
offline and private. Not needed for continuity above.

## Requirements

| | trace / collect | train / serve |
|---|---|---|
| **macOS (Apple Silicon)** | ✅ | ✅ MLX backend |
| **Linux** | ✅ | ✅ torch backend (CUDA or CPU) |
| **Windows** | ✅ | ✅ torch backend (CUDA or CPU) |
| **macOS (Intel)** | ✅ | ✅ torch backend (CPU) |

- [Claude Code](https://claude.com/claude-code) installed and used at least once (transcripts live in `~/.claude/projects`)
- Python 3.9+
- Node.js 18+ (only if installing via npm)

footprint picks the backend automatically: [MLX](https://github.com/ml-explore/mlx)
on Apple Silicon, PyTorch + PEFT everywhere else (uses CUDA when available;
CPU works but trains slowly — prefer a GPU or drop `FOOTPRINT_ITERS`).

## Install

### macOS

```sh
npm install -g footprint-trace
```

or from source:

```sh
git clone https://github.com/Amanlabh/footprint.git
cd footprint
python3 footprint.py setup
```

### Linux

```sh
npm install -g footprint-trace      # or the git clone above
```

First run installs the torch backend (one-time, ~2 GB). CUDA GPU picked up automatically.

### Windows

Use PowerShell (Python 3 from python.org or the Microsoft Store):

```powershell
npm install -g footprint-trace
```

Same as Linux: full trace/collect/train/serve via the torch backend. WSL2 also works.

## Getting started

**1. Arm tracing — before you start Claude.**

```sh
footprint trace
```

Claude Code already logs every session; the trace marker makes footprint train
only on sessions from this point on. (Skip this step — or delete
`~/.claude/footprint-trace` — to train on your entire history instead.)

**2. Use Claude Code normally.**

```sh
claude
```

Every session (your prompts, Claude's replies, tool calls) is captured automatically.

**3. Collect and train.**

```sh
footprint collect     # transcripts -> data/train.jsonl + data/valid.jsonl
footprint train       # LoRA fine-tune (~10 min, downloads ~1 GB base model first time)
```

**4. Install the always-on server.**

```sh
footprint install
```

This registers the server with your OS — launchd (macOS), systemd (Linux) or
Task Scheduler (Windows) — so it starts at login, restarts if it crashes, and
you never run it by hand. It also wires up OpenCode:

- provider `footprint` at `http://127.0.0.1:8399/v1`
- a `/footprint <task>` command inside OpenCode

**5. Claude quota over? Keep going.**

Open OpenCode and type:

```
/footprint fix the failing test in auth.py
```

Or point any OpenAI-compatible tool at the server:

| Tool | Setting |
|---|---|
| **Cursor** | Settings → Models → OpenAI base URL `http://127.0.0.1:8399/v1`, any API key, add model `footprint` |
| **Codex CLI** | custom provider with that base URL in `~/.codex/config.toml` |
| **anything else** | base URL `http://127.0.0.1:8399/v1`, API key: none |

## Commands

| Command | What it does |
|---|---|
| `footprint` | banner + status |
| `footprint trace` | arm tracing (run before starting Claude) |
| `footprint collect [dir]` | parse transcripts of a project (default: current dir; unknown dir = all projects) |
| `footprint train` | LoRA fine-tune on collected data |
| `footprint eval` | test loss + perplexity of the trained adapter on held-out data (lower = better) |
| `footprint install` | auto-start server (launchd / systemd / Task Scheduler) + OpenCode integration |
| `footprint context install` | continuity: new Claude Code sessions start with the previous session's state (goal, files, todos, last error, where it ended) via a SessionStart hook; OpenCode via plugin (+ `/continue` for open sessions); works both ways |
| `footprint context` | preview what the next session will be handed |
| `footprint serve` | run the server manually (fallback; `install` makes this unnecessary) |
| `footprint status` | model, example count, adapter, tracing, server state |

## Configuration

| Env var | Default | |
|---|---|---|
| `FOOTPRINT_MODEL` | `mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit` (mac) / `Qwen/Qwen2.5-Coder-1.5B-Instruct` | any chat model of the backend |
| `FOOTPRINT_ITERS` | auto | training iterations (unset = `FOOTPRINT_EPOCHS` passes over the train set, capped at `FOOTPRINT_ITERS_CAP`) |
| `FOOTPRINT_EPOCHS` | `3` | passes over the data when `FOOTPRINT_ITERS` is unset |
| `FOOTPRINT_ITERS_CAP` | `2000` | ceiling on auto iterations |
| `FOOTPRINT_BATCH` | `1` | batch size for train + eval |
| `FOOTPRINT_TEST_BATCHES` | `25` | batches scored by `eval` (`-1` = whole test split) |
| `FOOTPRINT_PORT` | `8399` | server port |
| `FOOTPRINT_CONTEXT_CAP` | `4000` | max chars of previous-session state injected (~1k tokens) |
| `FOOTPRINT_CONTEXT_MAX_AGE_H` | `168` | previous session older than this = stale, nothing injected |

## Troubleshooting

- **`no transcripts found`** — either you haven't used Claude Code in this project, or the trace marker is newer than all sessions. Chat first, or `rm ~/.claude/footprint-trace`.
- **server not responding** — macOS: `/tmp/footprint-serve.log`, `launchctl kickstart -k gui/$UID/com.footprint.serve`; Linux: `journalctl --user -u footprint`, `systemctl --user restart footprint`; Windows: `schtasks /Run /TN footprint-serve`.
- **backend import fails** (`mlx_lm` / `torch`) — re-run `footprint setup`.
- **quality is rough** — more data beats more iterations: keep tracing, re-collect, re-train. 1.5B is small; try `FOOTPRINT_MODEL=mlx-community/Qwen2.5-Coder-7B-Instruct-4bit` if you have ≥16 GB RAM.

## Privacy

Everything stays on your machine. `data/` (your transcripts) and `adapters/`
(weights trained on them) are gitignored — never commit or publish them.
