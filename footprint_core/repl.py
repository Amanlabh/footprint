"""footprint shell: type `footprint`, chat like Claude Code. Plain text = ask the model; /command = everything else.

Colors = the website's dark theme (UI-Web/app/globals.css, converted from oklch).
/login  browser sign-in: GitHub on the website -> key handed back to a one-shot listener on 127.0.0.1
/model  pick any model Ollama has downloaded; remembered in ~/.footprint/model
"""
import glob, http.server, json, math, os, secrets, shutil, sys, time, urllib.parse, urllib.request, webbrowser

from . import agent, ollama, vault

_rgb = lambda r, g, b: f"\x1b[38;2;{r};{g};{b}m"
PRI, FG, MUTED, ACC = _rgb(255, 109, 130), _rgb(249, 236, 225), _rgb(200, 161, 147), _rgb(211, 240, 184)
B, R = "\x1b[1m", "\x1b[0m"
MODEL_FILE = os.path.join(vault.HOME, "model")
CHATS = os.path.join(vault.HOME, "chats")  # one JSON per shell chat: /resume reloads it
CLI = ["status", "trace", "collect", "train", "eval", "adapter", "serve", "install", "context", "switch",
       "recall", "profile", "facts", "memory", "bench", "setup", "key", "sync"]
OWN = {"help": "this list", "login": "sign in through the website (GitHub)", "logout": "sign out on this computer",
       "model": "pick a downloaded model: /model, /model 2, /model qwen2.5-coder:7b",
       "resume": "continue an earlier chat: /resume, /resume 2", "clear": "start a new conversation",
       "exit": "quit (or Ctrl-D)"}
CHAT = {"id": time.strftime("%Y%m%d-%H%M%S"), "history": []}  # the chat on screen; /resume and /clear swap it


def say(text, color=FG):
    print(f"{color}{text}{R}")


def models():
    with urllib.request.urlopen(ollama.URL + "/api/tags", timeout=5) as r:
        return [m["name"] for m in json.load(r)["models"]
                if "embed" not in m["name"] and "bert" not in m.get("details", {}).get("family", "")]  # not chat models


def model_cmd(args):
    try:
        names = models()
    except OSError:
        return say("Ollama isn't running. Open the Ollama app (or `ollama serve`), then /model again.", PRI)
    if not names:
        return say("no models downloaded. e.g. `ollama pull qwen2.5-coder:7b`, or `/install` for your trained one.", PRI)
    pick = args[0] if args else None
    if pick is None:
        for i, n in enumerate(names, 1):
            cur = n == agent.MODEL or n.split(":")[0] == agent.MODEL
            say(f"  {i}. {n}{'  ← current' if cur else ''}", ACC if cur else FG)
        pick = input(f"{MUTED}number (Enter = keep): {R}").strip()
        if not pick:
            return
    name = names[int(pick) - 1] if pick.isdigit() and 0 < int(pick) <= len(names) else pick
    if name not in names and f"{name}:latest" not in names:
        return say(f"no downloaded model '{name}'. /model lists them.", PRI)
    agent.MODEL = name
    os.makedirs(vault.HOME, exist_ok=True)
    open(MODEL_FILE, "w", encoding="utf-8").write(name)
    say(f"model → {name}", ACC)


def login_cmd(args):
    if args:  # /login fp_… still works (key pasted from the website)
        return vault.login(args)
    state, got = secrets.token_hex(16), {}

    class Back(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            ok = q.get("state", [""])[0] == state and q.get("key", [""])[0].startswith("fp_")
            if ok:
                got["key"] = q["key"][0]
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Signed in. You can close this tab and go back to the terminal." if ok else "Sign-in failed. Run /login again."
            self.wfile.write(f"<body style='background:#2a1717;color:#f9ece1;font:16px system-ui;padding:40px'>"
                             f"<b style='color:#ff6d82'>footprint</b><p>{msg}</p>".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Back)
    srv.timeout = 1
    url = f"{vault.API}/api/auth/cli?port={srv.server_port}&state={state}"
    say("opening the browser to sign in with GitHub…", MUTED)
    say(f"  if it doesn't open: {url}", MUTED)
    webbrowser.open(url)
    end = time.time() + 300
    try:
        while "key" not in got and time.time() < end:
            srv.handle_request()
    except KeyboardInterrupt:
        got.clear()
    srv.server_close()
    if "key" not in got:
        return say("login cancelled or timed out.", PRI)
    vault.key_login(got["key"])


def logout_cmd(_):
    for f in (vault.KEY_FILE, vault.TOKEN_FILE):
        if os.path.exists(f):
            os.remove(f)
    say("signed out on this computer. (keys stay listed on the website until you revoke them)", MUTED)


def save_chat():
    if CHAT["history"]:
        os.makedirs(CHATS, exist_ok=True)
        tmp = os.path.join(CHATS, CHAT["id"] + ".tmp")
        json.dump({"cwd": os.getcwd(), "history": CHAT["history"]}, open(tmp, "w", encoding="utf-8"))
        os.replace(tmp, os.path.join(CHATS, CHAT["id"] + ".json"))


def past_chats():
    """Saved chats, newest first, minus the one on screen -> [(id, data, mtime)]"""
    out = []
    for f in sorted(glob.glob(os.path.join(CHATS, "*.json")), key=os.path.getmtime, reverse=True):
        cid = os.path.basename(f)[:-5]
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if cid != CHAT["id"] and d.get("history"):
            out.append((cid, d, os.path.getmtime(f)))
    return out


def resume_cmd(args):
    past = past_chats()[:10]
    if not past:
        return say("no earlier chats saved yet.", MUTED)
    pick = args[0] if args else None
    if pick is None:
        for i, (_, d, m) in enumerate(past, 1):
            h = (time.time() - m) / 3600
            when = f"{h * 60:.0f}m" if h < 1 else f"{h:.0f}h" if h < 24 else f"{h / 24:.0f}d"
            first = d["history"][0]["content"].replace("\n", " ")[:56]
            print(f"  {PRI}{i:>2}.{R} {FG}{first}{R}  {MUTED}{when} ago · {len(d['history']) // 2} msgs · "
                  f"{d.get('cwd', '').replace(os.path.expanduser('~'), '~')}{R}")
        pick = input(f"{MUTED}number (Enter = cancel): {R}").strip()
        if not pick:
            return
    if not (pick.isdigit() and 0 < int(pick) <= len(past)):
        return say(f"no chat {pick}. /resume lists them.", PRI)
    cid, d, _ = past[int(pick) - 1]
    CHAT["id"], CHAT["history"][:] = cid, d["history"]
    h = CHAT["history"]
    if len(h) > 6:
        say(f"  … {len(h) - 6} earlier messages", MUTED)
    for m in h[-6:]:  # the tail on screen; the model gets the whole chat
        say(f"❯ {m['content']}" if m["role"] == "user" else m["content"], MUTED if m["role"] == "user" else FG)
    say(f"resumed ({len(h) // 2} msgs). carry on.", ACC)


def help_cmd(_):
    say("type a question or a task. footprint uses tools (shell, files, web search) when it needs them.", MUTED)
    for k, v in OWN.items():
        print(f"  {PRI}/{k:<9}{R}{FG}{v}{R}")
    say("  footprint commands:", MUTED)
    from .cli import __doc__ as doc
    shown = set()
    for line in doc.splitlines():
        w = line.strip().split(" ")[0]
        if w in CLI and w not in shown:
            shown.add(w)
            print(f"  {PRI}/{line.strip()}{R}")


def run_cli(cmd, args):
    from . import cli  # lazy: cli imports this module
    try:
        cli.main([cmd, *args])
    except SystemExit as e:
        if isinstance(e.code, str):
            say(e.code, PRI)


# the website's pixel octocat (UI-Web/app/icon.svg, 12x12), two pixels per character
LOGO = ["  █▄    ▄█  ", " ▄████████▄ ", " █▄██████▄█ ", "  ████████  ", "  █▀▀██▀▀█  ", " ▄▀  ▀▀  ▀▄ "]
LOGO_C = PRI  # the website draws it in text-primary (dark theme: oklch(0.72 0.18 14))


def header():
    name = "signed in" if os.path.exists(vault.KEY_FILE) else "not signed in · /login"
    w = min(shutil.get_terminal_size().columns, 72)
    info = ["", f"{B}footprint{R}{FG}  your Claude, learned locally",
            f"{MUTED}model {agent.MODEL} · {name}",
            f"{MUTED}{os.getcwd().replace(os.path.expanduser('~'), '~')}",
            f"{MUTED}/help for commands · /model to switch · Ctrl-D to quit", ""]
    print(f"{PRI}╭{'─' * (w - 2)}╮{R}")
    for art, line in zip(LOGO, info):
        print(f"{PRI}│{R} {LOGO_C}{art}{R}  {line}{R}")
    print(f"{PRI}╰{'─' * (w - 2)}╯{R}")


def prompt():
    """Claude Code-style input box: rule, ❯ line, rule, status underneath. -> the typed line.
    After Enter the box is replaced by the message itself, like a chat transcript."""
    if not sys.stdin.isatty():  # piped / scripted: plain prompt
        return input(f"\n{PRI}{B}>{R} ")
    w = shutil.get_terminal_size().columns
    rule = f"{MUTED}{'─' * w}{R}"
    who = "signed in" if os.path.exists(vault.KEY_FILE) else "not signed in · /login"
    print(f"\n{rule}\n\n{rule}\n{MUTED}  {agent.MODEL} · {who} · /help for commands{R}", end="")
    print("\x1b[2A\r", end="", flush=True)  # cursor back up from the status line to the empty line inside the box
    try:
        line = input(f"\001{FG}{B}\002❯\001{R}\002 ")  # \001..\002: readline doesn't count the color codes
    except (EOFError, KeyboardInterrupt):
        print("\n\x1b[J", end="")  # drop the rest of the box
        raise
    up = max(1, math.ceil((len(line) + 2) / w)) + 1  # the typed line(s) + the top rule
    print(f"\x1b[{up}A\r\x1b[J{MUTED}❯ {line}{R}", flush=True)  # box -> plain transcript line
    return line


def styled(line):  # the agent's progress lines vs its answer
    s = str(line)
    say(s, MUTED if s.startswith("· ") else ACC if s.startswith("  [") else FG)


def main():
    if os.path.exists(MODEL_FILE) and "FOOTPRINT_AGENT_MODEL" not in os.environ:
        agent.MODEL = open(MODEL_FILE, encoding="utf-8").read().strip() or agent.MODEL
    try:
        import readline
        names = ["/" + c for c in [*OWN, "quit", *CLI]]
        readline.set_completer(lambda t, i: ([n for n in names if n.startswith(t)] + [None])[i])
        readline.set_completer_delims(" ")
        readline.parse_and_bind("bind ^I rl_complete" if "libedit" in (readline.__doc__ or "") else "tab: complete")
    except ImportError:  # Windows
        pass
    header()
    own = {"help": help_cmd, "login": login_cmd, "logout": logout_cmd, "model": model_cmd, "resume": resume_cmd}
    while True:
        try:
            line = prompt().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line:
            continue
        try:
            if line.startswith("/"):
                cmd, *args = line[1:].split()
                if cmd in ("exit", "quit"):
                    return
                if cmd == "clear":
                    CHAT["id"], CHAT["history"] = time.strftime("%Y%m%d-%H%M%S"), []
                    say("new conversation.", MUTED)
                elif cmd in own:
                    own[cmd](args)
                elif cmd in CLI:
                    run_cli(cmd, args)
                else:
                    say(f"unknown command /{cmd}. /help lists them.", PRI)
                continue
            agent.ask([line], out=styled, history=CHAT["history"])
            save_chat()
        except KeyboardInterrupt:
            say("\ninterrupted.", MUTED)
        except OSError as e:
            say(f"can't reach the model at {ollama.URL} ({e}). Start Ollama, or /model to pick another.", PRI)


if __name__ == "__main__":  # self-check: chats save, list newest-first without the current one, resume loads
    import tempfile
    CHATS = tempfile.mkdtemp()
    CHAT.update(id="a", history=[{"role": "user", "content": "first q"}, {"role": "assistant", "content": "first a"}])
    save_chat()
    time.sleep(0.01)
    CHAT.update(id="b", history=[{"role": "user", "content": "second q"}, {"role": "assistant", "content": "second a"}])
    save_chat()
    assert [c[0] for c in past_chats()] == ["a"]  # b is on screen
    CHAT.update(id="c", history=[])
    save_chat()  # empty chat: not saved
    assert [c[0] for c in past_chats()] == ["b", "a"]
    say = lambda *a: None
    resume_cmd(["2"])
    assert CHAT["id"] == "a" and CHAT["history"][1]["content"] == "first a"
    CHAT["history"] += [{"role": "user", "content": "more"}, {"role": "assistant", "content": "ok"}]
    save_chat()  # resumed chat keeps saving into its own file
    assert len(json.load(open(os.path.join(CHATS, "a.json")))["history"]) == 4
    print("repl self-check ok")
