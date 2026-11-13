# footprint — New User Guide

Claude ran out? Keep going on a free model that already knows what you were doing.
Same steps as **Get started** on https://www.tracefootprint.space/account.

Steps 1–7 are required (about two minutes). 8–10 are optional.

---

## 1. Check you have Python 3

```sh
python3 --version
```

Nothing else needed — no npm, no git. macOS / Linux for now (Windows coming).
No Python on macOS? `xcode-select --install`.

## 2. Generate your key

1. Open https://www.tracefootprint.space/account → **Continue with GitHub** → **Authorize**.
   (footprint creates a private `footprint-vault` repo in your GitHub — your data lives there, not with us.)
2. Type a label (e.g. `macbook`) → **Generate API key**.
3. The key is shown **once**, with the install command already filled in. Copy that command.

## 3. Install + sign in

Paste the copied command in your terminal:

```sh
curl -fsSL https://www.tracefootprint.space/install.sh | sh -s -- fp_yourkey
```

Installs footprint into `~/.footprint/app`, signs you in, and hooks into Claude Code and OpenCode.

## 4. Open a new terminal and check it works

```sh
footprint context
```

Prints your last session in this folder — or "no previous session", which is fine on day one.

## 5. Get OpenCode (your free fallback)

```sh
curl -fsSL https://opencode.ai/install | bash
```

Free coding agent with free models (Big Pickle). Skip if you have it.

## 6. Work in Claude Code as usual

```sh
cd my-project
claude
```

Nothing to change. footprint remembers each session: goal, files, todos, last error, how tasks were solved.

## 7. Claude ran out? Open OpenCode in the same project

```sh
cd my-project
opencode
```

- The new session already knows where you stopped.
- Every prompt also gets your **similar past work** from all your sessions — any model.
- Pick a model with `/models` (Big Pickle is free).
- Chat already open? Type `/continue`.

---

## 8. (Optional) Want the exact same chat instead?

```sh
footprint switch
```

Moves your whole Claude Code conversation into OpenCode, message by message.
`footprint switch list` shows session ids; `footprint switch <id>` opens a specific one.

## 9. (Optional) Measure which free model works best for you

```sh
footprint bench harvest
footprint bench run opencode/big-pickle --memory=both
footprint bench upload
```

Replays tasks Claude finished in your repos with any model and scores them.
Scores (numbers only — never prompts or code) appear under **Claude parity** on your account,
where you can create a public share link + README badge.

## 10. (Optional, advanced) Train a local model on your sessions

An offline model that learned from your Claude sessions. Needs an Apple Silicon Mac with 16GB+
(or an NVIDIA GPU) and makes it hot while training. Honest note: the base model is small (1.5B) —
it picks up style but is weak at agent tasks; check it with `footprint bench`.

Run these in order:

| # | Command | What it does | Why it's needed |
|---|---|---|---|
| a | `footprint setup` | Creates a private Python environment (`~/.footprint/app/.venv`) and installs the training engine — MLX on a Mac, PyTorch + transformers on Linux/Windows (~2 GB). One time. | Training libraries are large; their own environment keeps your system Python untouched. `train`/`eval`/`serve`/`install` run it for you if you skip it. |
| b | `footprint trace` | Marks "now": only Claude sessions from this moment on become training data. | You choose what the model learns from. Skip it to train on all past sessions. |
| c | *…work with Claude Code for a while* | Use Claude normally on real tasks. | These sessions are the lessons — more sessions, better model. |
| d | `footprint collect` | Turns your Claude sessions into examples: "conversation so far → what Claude did next". Keeps 10% aside for testing. | A model needs example pairs, not raw transcripts. The 10% is what `eval` tests on. |
| e | `footprint train` | LoRA fine-tune: a small add-on (~20 MB adapter) on top of the base model (Qwen2.5-Coder 1.5B). Minutes to hours; laptop gets hot. | Teaches your and Claude's working style without changing the base model. |
| f | `footprint eval` | Scores the trained model on the 10% it never saw (loss + perplexity — lower is better). | Confirms it learned before you rely on it. Measures text prediction, not task success — use `footprint bench` for that. |
| g | `footprint install` | Builds a "footprint" model in Ollama (your adapter on `qwen2.5-coder:1.5b`) at `localhost:11434`; Ollama starts at login. Adds a "footprint" model + `/footprint` command to OpenCode. | You never start it by hand — in OpenCode pick the footprint model with `/models`. |
| h | `footprint serve` | Rebuilds the Ollama "footprint" model from the live adapter. | Only if you changed adapters by hand. `install` and `adapter use` already do it. |
| i | `footprint status` | Engine (mlx / torch), base model, number of training examples, adapter yes/no. | Quick check of where you are in these steps. |

---

## All commands

| Command | What it does |
|---|---|
| `/continue [next task]` | Inside OpenCode: pull the last session's state into a chat that was already open |
| `/clear` | Inside Claude Code: fresh chat that still starts with the last session's state |
| `footprint login fp_…` | Sign in on this device |
| re-run the install command | Update footprint (your data is kept) |
| `footprint context` | Preview what the next session will be handed |
| `footprint context install` | (Re)install the Claude Code hooks + OpenCode plugin |
| `footprint recall <text>` | Similar past work footprint adds to a prompt like that |
| `footprint switch [list \| <id>]` | Open a Claude Code chat in OpenCode, full history |
| `footprint bench harvest [n]` | Pick tasks Claude finished as the answer key |
| `footprint bench run <provider/model>… --memory=both` | Replay them with any model |
| `footprint bench` / `bench upload` | Show the report / send scores to your account |
| `footprint setup` | One-time local model backend install (runs automatically) |
| `footprint trace` · `collect` · `train` · `eval` | Local model: arm tracing, build data, train, test |
| `footprint install` · `serve` · `status` | Local model: keep running, run by hand, show state |

## If something goes wrong

- **`footprint: command not found`** — open a new terminal (step 4).
- **"key rejected"** — revoked, mistyped, or made before 2 Nov 2026. Generate a new one on the account page.
- **No handover in a new session** — run `footprint context` in that folder. "No previous session" = nothing recent there yet.
- **Lost a key** — Revoke it on the account page; every machine using it stops.
