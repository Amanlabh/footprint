"""footprint shell: type `footprint`, chat like Claude Code. Plain text = ask the model; /command = everything else.

Colors = the website's dark theme (UI-Web/app/globals.css, converted from oklch).
/login  browser sign-in: GitHub on the website -> key handed back to a one-shot listener on 127.0.0.1
/model  pick any model Ollama has downloaded; remembered in ~/.footprint/model
"""
import http.server, json, os, secrets, shutil, time, urllib.parse, urllib.request, webbrowser

from . import agent, ollama, vault

_rgb = lambda r, g, b: f"\x1b[38;2;{r};{g};{b}m"
PRI, FG, MUTED, ACC = _rgb(255, 109, 130), _rgb(249, 236, 225), _rgb(200, 161, 147), _rgb(211, 240, 184)
B, R = "\x1b[1m", "\x1b[0m"
MODEL_FILE = os.path.join(vault.HOME, "model")
CLI = ["status", "trace", "collect", "train", "eval", "adapter", "serve", "install", "context", "switch",
       "recall", "profile", "facts", "memory", "bench", "setup", "key", "sync"]
OWN = {"help": "this list", "login": "sign in through the website (GitHub)", "logout": "sign out on this computer",
       "model": "pick a downloaded model: /model, /model 2, /model qwen2.5-coder:7b",
       "clear": "start a new conversation", "exit": "quit (or Ctrl-D)"}


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
LOGO_C = _rgb(229, 72, 111)  # #e5486f, the icon's fill


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
    history = []
    own = {"help": help_cmd, "login": login_cmd, "logout": logout_cmd, "model": model_cmd}
    while True:
        try:
            line = input(f"\n{PRI}{B}>{R} ").strip()
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
                    history.clear()
                    say("new conversation.", MUTED)
                elif cmd in own:
                    own[cmd](args)
                elif cmd in CLI:
                    run_cli(cmd, args)
                else:
                    say(f"unknown command /{cmd}. /help lists them.", PRI)
                continue
            agent.ask([line], out=styled, history=history)
        except KeyboardInterrupt:
            say("\ninterrupted.", MUTED)
        except OSError as e:
            say(f"can't reach the model at {ollama.URL} ({e}). Start Ollama, or /model to pick another.", PRI)
