# footprint

**Your Claude, learned locally.**

Footprint watches your Claude Code sessions, fine-tunes a small local model
(LoRA) on how *you and Claude* work in your projects, and serves it as an
OpenAI-compatible API. When your Claude quota runs out, OpenCode (or Cursor,
or Codex CLI) keeps working in the same style — fully offline, on your machine.

```
trace → chat with claude → collect → train → install → /footprint in OpenCode
```

## How it works

1. Claude Code already logs every session (prompts, replies, tool calls) to `~/.claude/projects`.
2. `footprint trace` arms a marker so only sessions from that point on become training data.
3. `footprint collect` parses those transcripts into chat-format training examples.
4. `footprint train` LoRA fine-tunes a small model (default: Qwen2.5-Coder-1.5B, 4-bit MLX) on them.
5. `footprint install` registers a launchd agent — the server runs itself at
   `http://127.0.0.1:8399/v1`, starts at login, restarts on crash. You never run it by hand.
6. Any OpenAI-compatible tool points at that URL and behaves like your Claude.

## Requirements

| | trace / collect | train / serve |
|---|---|---|
| **macOS (Apple Silicon)** | ✅ | ✅ (MLX) |
| **macOS (Intel)** | ✅ | ❌ |
| **Linux** | ✅ | ❌ (for now) |
| **Windows** | ✅ | ❌ (for now) |

- [Claude Code](https://claude.com/claude-code) installed and used at least once
- Python 3.9+
- Node.js 18+ (only if installing via npm)

Training and serving use [MLX](https://github.com/ml-explore/mlx), which is
Apple-Silicon-only today. On Linux/Windows you can still trace and collect —
your `data/` folder is portable; train it on any Apple Silicon Mac. Other
backends (llama.cpp / unsloth) are welcome contributions.

## Install

### macOS

```sh
npm install -g Amanlabh/footprint
```

or from source:

```sh
git clone https://github.com/Amanlabh/footprint.git
cd footprint
python3 footprint.py setup
```

### Linux

```sh
npm install -g Amanlabh/footprint      # or the git clone above
```

`setup` skips MLX automatically. `trace` and `collect` work; copy `data/` to a Mac to train.

### Windows

Use PowerShell (Python 3 from python.org or the Microsoft Store):

```powershell
npm install -g Amanlabh/footprint
```

Same scope as Linux: trace + collect. WSL2 works the same way.

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

**4. Install the always-on server (macOS).**

```sh
footprint install
```

This registers a launchd agent — the server starts at login, restarts if it
crashes, and you never run it by hand. It also wires up OpenCode:

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
| `footprint install` | launchd auto-server + OpenCode integration (macOS) |
| `footprint serve` | run the server manually (fallback; `install` makes this unnecessary) |
| `footprint status` | model, example count, adapter, tracing, server state |

## Configuration

| Env var | Default | |
|---|---|---|
| `FOOTPRINT_MODEL` | `mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit` | any MLX chat model |
| `FOOTPRINT_ITERS` | `300` | training iterations |
| `FOOTPRINT_PORT` | `8399` | server port |

## Troubleshooting

- **`no transcripts found`** — either you haven't used Claude Code in this project, or the trace marker is newer than all sessions. Chat first, or `rm ~/.claude/footprint-trace`.
- **server not responding** — check `/tmp/footprint-serve.log`; `launchctl kickstart -k gui/$UID/com.footprint.serve` restarts it.
- **`mlx_lm` import fails** — re-run `footprint setup` (Apple Silicon only).
- **quality is rough** — more data beats more iterations: keep tracing, re-collect, re-train. 1.5B is small; try `FOOTPRINT_MODEL=mlx-community/Qwen2.5-Coder-7B-Instruct-4bit` if you have ≥16 GB RAM.

## Privacy

Everything stays on your machine. `data/` (your transcripts) and `adapters/`
(weights trained on them) are gitignored — never commit or publish them.

## License

MIT — see [LICENSE](LICENSE).
