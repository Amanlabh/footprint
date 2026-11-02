# footprint — New User Guide

How a new user goes from zero to "my AI session remembers where I left off".

> Planned flow. ✅ = works today · 🔨 = still to build

---

## Before you start

- **Python 3.9+** (macOS: already there, or `xcode-select --install`). No npm, no git.
- A coding tool — any one:
  - **OpenCode** (free): `curl -fsSL https://opencode.ai/install | bash`
  - **Claude Code**, if you already pay for Claude

---

## Step 1 — Create an account (1 minute)

1. Open https://www.tracefootprint.space/account → click **Continue with GitHub**. ✅
2. GitHub asks permission → **Authorize**. ✅
   - footprint creates a private repo `footprint-vault` in your GitHub. Your synced sessions live there — not with us.
   - 🔨 Permission will shrink to "access to footprint-vault only" (GitHub App instead of OAuth `repo` scope).
3. You land on the **API keys** page. ✅

## Step 2 — Get your key

4. Type a label (e.g. `macbook`) → **Generate API key**. ✅
5. The page shows a ready command with your key in it. Copy it. **Shown only once.** Lost it? Generate a new one, revoke the old. ✅

## Step 3 — Connect your machine (one command)

6. In your terminal:

   ```sh
   curl -fsSL https://www.tracefootprint.space/install.sh | sh -s -- fp_xxxxxxxx
   ```

   ✅ Live. Installs into `~/.footprint/app`, puts `footprint` in `~/.local/bin`. Re-run to update.

   This one command:
   - saves your key in `~/.footprint/` (only you can read it)
   - installs the handover into Claude Code and OpenCode
   - adds a **footprint** model provider to OpenCode — no model setup needed 🔨
   - prints: `signed in as <you> · context sync on · model: footprint/glm-5.3`

## Step 4 — Start working

7. Open any project and start your tool:

   ```sh
   cd my-project
   opencode
   ```

8. Work normally. First session has nothing to hand over yet.

## Step 5 — Come back later: footprint takes over

9. Next time you open OpenCode or Claude Code in that project, the new session already knows:
   - goal, files touched, open todos
   - last error, and where you stopped

   Switching tools mid-task: ✅
   - Claude ↔ OpenCode: just open the other tool — it continues.
   - Want the exact same chat in OpenCode? `footprint switch`

## Step 6 — Another laptop

10. On the second machine, same command, same key (or a new one):

    ```sh
    curl -fsSL https://www.tracefootprint.space/install.sh | sh -s -- fp_xxxxxxxx
    ```

11. Open the project → continues from where you left off on laptop 1 (handover synced through your `footprint-vault`). 🔨

---

## Everyday commands

| Command | What it does |
|---|---|
| `footprint context` | Preview what will be handed over ✅ |
| `footprint status` | Signed-in user, today's model usage, sync on/off 🔨 |
| `footprint sync off` | Keep everything on this machine (private / company code) 🔨 |
| Website → **Revoke** | Kill a lost key; every machine using it stops ✅ |
| Re-run the install command | Update footprint (keeps your data) ✅ |

## If something goes wrong

- **"key invalid"** — revoked or mistyped. Generate a new one on the website.
- **"daily limit reached"** — free model cap hit. Resets tomorrow, or pick another model in OpenCode with `/models`.
- **No handover in a new session** — run `footprint context`. Empty output = no recent session in that project yet.
