# footprint — Known Gaps

Open issues in the website-key + curl-installer flow. Newest work: `2ac2e83` (2026-11-02).

## Install

| Gap | Impact | Fix |
|---|---|---|
| **No Windows installer** | `install.sh` is macOS/Linux only; npm used to cover Windows | `install.ps1` (`irm https://www.tracefootprint.space/install.ps1 \| iex`) |
| **Installer ships `main` tip** | Every push to `main` reaches users on next install/update — a broken commit breaks everyone | Point installer at tagged GitHub releases |
| **Key in shell history** | `… \| sh -s -- fp_key` leaves the key in `~/.zsh_history` | Accept (revoke kills a leaked key) or prompt for the key instead of an argument |
| **Removed files linger on update** | Re-install overwrites `footprint_core/` + `skills/` only; deleted files elsewhere in `~/.footprint/app` stay | Fine for now; wipe all code paths except `data/ adapters/ .venv/` if it bites |
| **npm package stale** | npm has `0.2.0` (no key login); footer still links npm | Unpublish/deprecate or publish once more; remove footer link |
| **Needs python3** | Machines without Python can't install | macOS: `xcode-select --install`; or ship a single binary later |

## Keys & auth

| Gap | Impact | Fix |
|---|---|---|
| **Real-key end-to-end test pending** | Only the reject paths are verified on production | Sign in on `/account`, generate a key, run the shown command |
| **GitHub OAuth asks `repo` scope** | Read/write to *all* user's private repos — businesses/enterprises will refuse | GitHub App with access to `footprint-vault` only |
| **Old keys invalid** | Keys made before `050bd7f` are rejected | Regenerate on the website |
| **`SESSION_SECRET` rotation kills all keys** | Changing the secret logs every user out of every machine | Never rotate casually; support two secrets during a rotation if needed |
| **Key verify = 1 GitHub API call** | Fine for login; too slow / rate-limited for a model gateway | Cache verified keys (short TTL) when the gateway lands |
| **CLI `sync push\|pull` + `key list\|revoke` still use GitHub device flow** | Needs `FOOTPRINT_GITHUB_CLIENT_ID`, which is empty by default → broken for users | Move sync/keys to the server, authenticated by the `fp_` key (step 2) |

## Not built yet

| Gap | Notes |
|---|---|
| **Step 2 — cloud context sync** | Handover saved to the user's vault, read on another machine; `footprint sync off` for private/company code |
| **Step 3 — model gateway** | `/api/v1/chat/completions` with the key; `login` adds a `footprint` provider to `opencode.json` |
| **`footprint status` (account view)** | Signed-in user, today's usage, sync on/off |

## Model gateway — decide before building

| Gap | Notes |
|---|---|
| **Who pays** | Every model call costs; free upstream tiers (Ollama cloud, OpenRouter) are per-account limited, so one shared key gets throttled at scale |
| **Needs a store** | Per-user daily counts can't live in serverless memory → Neon or Upstash Redis |
| **Provider terms** | Reselling another provider's free tier may break their terms — check first |
| **Upstream choice** | GLM 5.3 via Ollama cloud, OpenRouter, Gemini, … — pick one |

## Bench (`footprint bench`)

| Gap | Notes |
|---|---|
| **Few qualifying tasks** | Needs Claude tasks that ran a check *and* ended in a commit; this machine had 1–2. More sessions → sharper parity |
| **Question-style prompts** | "isn't it possible to…" — a replayed model may answer instead of editing; scored as fail |
| **No AI judge yet** | Pass = check passes + files changed; diff-equivalence judging not built |
| **Deps borrowed by symlink** | `node_modules`/`.venv` from the real repo; tasks needing other installs may fail |
| **Share links can't be revoked one by one** | Stateless sealed links; rotating `SESSION_SECRET` kills all (and all API keys) |
| **Team view** | Needs team/org accounts, which don't exist yet |
| **OpenCode trusts `$PWD`** | Launching OpenCode from code with an inherited `PWD` makes it edit *that* directory. Bench pins `PWD` + `--dir`; anything new that spawns OpenCode must too |

## Enterprise

| Gap | Notes |
|---|---|
| **Session data leaves the machine with sync** | Needs opt-out (and probably default-off for orgs) |
| **No org/team accounts** | Keys and vaults are per GitHub user only |
