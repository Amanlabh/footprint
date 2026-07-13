"""trace / status / setup / install — everything that isn't parsing or the model."""
import json, os, plistlib, subprocess, sys, time

from . import config


def trace():
    """Arm tracing. Claude Code already logs every session to ~/.claude/projects;
    the marker makes collect use only sessions started after this moment."""
    os.makedirs(os.path.dirname(config.TRACE_MARK), exist_ok=True)
    with open(config.TRACE_MARK, "w") as f:
        f.write(str(time.time()))
    print("tracing armed. chat with Claude Code as usual — those sessions become training data.\n"
          "then: footprint collect && footprint train\n"
          "(delete ~/.claude/footprint-trace to collect ALL history again)")


def status():
    tr = os.path.join(config.DATA, "train.jsonl")
    n = sum(1 for _ in open(tr)) if os.path.exists(tr) else 0
    installed = os.path.exists(config.LAUNCHD) if config.IS_MAC else \
        os.path.exists(config.SYSTEMD) if not config.IS_WIN else \
        subprocess.run(["schtasks", "/Query", "/TN", "footprint-serve"],
                       capture_output=True).returncode == 0
    print(f"backend: {'mlx' if config.IS_MAC else 'torch'}\nmodel: {config.MODEL}\nexamples: {n}\n"
          f"adapter: {'yes' if config.has_adapter() else 'no'}\n"
          f"tracing: {'armed since ' + time.ctime(float(open(config.TRACE_MARK).read())) if os.path.exists(config.TRACE_MARK) else 'off (collect uses all history)'}\n"
          f"server: {'auto-managed' if installed else 'not installed (run install)'}")


def setup():
    venv = os.path.join(config.ROOT, ".venv")
    if not os.path.exists(venv):
        subprocess.run([sys.executable, "-m", "venv", venv], check=True)
    pkgs = ["mlx-lm"] if config.IS_MAC else ["torch", "transformers", "peft", "trl", "datasets"]
    if not config.IS_MAC:
        print("installing torch + transformers stack (one-time, ~2 GB)…")
    subprocess.run([config.VENV_PY, "-m", "pip", "install", "-q", *pkgs], check=True)
    link = os.path.expanduser("~/.claude/skills/footprint")
    try:
        os.makedirs(os.path.dirname(link), exist_ok=True)
        if not os.path.exists(link):
            os.symlink(os.path.join(config.ROOT, "skills", "footprint"), link)
    except OSError:
        pass  # Windows without symlink rights — skill is optional
    print(f"ready. next: footprint trace")


def _opencode():
    cfg_path = os.path.join(config.OPENCODE, "opencode.json")
    cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {"$schema": "https://opencode.ai/config.json"}
    cfg.setdefault("provider", {})["footprint"] = {
        "npm": "@ai-sdk/openai-compatible", "name": "footprint",
        "options": {"baseURL": f"http://127.0.0.1:{config.PORT}/v1"},
        "models": {"footprint": {"name": "footprint"}}}
    os.makedirs(os.path.join(config.OPENCODE, "command"), exist_ok=True)
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)
    with open(os.path.join(config.OPENCODE, "command", "footprint.md"), "w") as f:
        f.write("---\ndescription: do task with footprint — local model trained on your Claude sessions\n"
                "model: footprint/footprint\n---\n$ARGUMENTS\n")


def install():
    """Register the server with the OS so it runs itself. User never runs serve."""
    if not os.path.exists(config.VENV_PY):
        sys.exit("no .venv. run: footprint setup")
    if config.IS_MAC:
        os.makedirs(os.path.dirname(config.LAUNCHD), exist_ok=True)
        with open(config.LAUNCHD, "wb") as f:
            plistlib.dump({"Label": "com.footprint.serve",
                           "ProgramArguments": [config.VENV_PY, config.ENTRY, "serve"],
                           "RunAtLoad": True, "KeepAlive": True,
                           "StandardOutPath": "/tmp/footprint-serve.log",
                           "StandardErrorPath": "/tmp/footprint-serve.log"}, f)
        subprocess.run(["launchctl", "unload", config.LAUNCHD], capture_output=True)
        subprocess.run(["launchctl", "load", "-w", config.LAUNCHD], check=True)
        how = "launchd (log: /tmp/footprint-serve.log)"
    elif config.IS_WIN:
        subprocess.run(["schtasks", "/Create", "/F", "/TN", "footprint-serve", "/SC", "ONLOGON",
                        "/TR", f'"{config.VENV_PY}" "{config.ENTRY}" serve'], check=True)
        subprocess.run(["schtasks", "/Run", "/TN", "footprint-serve"], check=True)
        how = "Task Scheduler (task: footprint-serve)"
    else:
        os.makedirs(os.path.dirname(config.SYSTEMD), exist_ok=True)
        with open(config.SYSTEMD, "w") as f:
            f.write("[Unit]\nDescription=footprint local model server\n\n"
                    f"[Service]\nExecStart={config.VENV_PY} {config.ENTRY} serve\nRestart=always\n\n"
                    "[Install]\nWantedBy=default.target\n")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "footprint"], check=True)
        how = "systemd --user (journalctl --user -u footprint)"
    _opencode()
    print(f"installed:\n"
          f"  server: {how} keeps http://127.0.0.1:{config.PORT}/v1 running\n"
          f"  opencode: /footprint <task> uses it; or pick model 'footprint' via /models\n"
          f"  cursor/codex: base URL http://127.0.0.1:{config.PORT}/v1, any api key")
