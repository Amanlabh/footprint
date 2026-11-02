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

Needs an Apple Silicon Mac with 16GB+ (or an NVIDIA GPU) — it heats the laptop.

```sh
footprint trace      # first: only sessions from now on become training data
# …work for a while…
footprint collect
footprint train
footprint eval
footprint install    # keeps it running; shows up in OpenCode as "footprint"
```

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
