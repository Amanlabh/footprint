#!/usr/bin/env python3
"""footprint — learn a local SLM from your Claude Code transcripts.

Commands:
  setup                 create .venv, install mlx-lm, link /footprint skill
  trace                 arm tracing: sessions from now on become training data (run before chatting)
  collect [project]     parse ~/.claude/projects transcripts -> data/{train,valid}.jsonl
  train                 LoRA fine-tune base model on collected data
  serve                 OpenAI-compatible API at localhost:8399 (launchd runs this; users don't)
  install               launchd agent (server always on) + OpenCode /footprint command
  status                what's collected/trained
"""
import json, os, re, subprocess, sys, glob, random, time, plistlib

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
ADAPTERS = os.path.join(ROOT, "adapters")
PROJECTS = os.path.expanduser("~/.claude/projects")
TRACE_MARK = os.path.expanduser("~/.claude/footprint-trace")
LAUNCHD = os.path.expanduser("~/Library/LaunchAgents/com.footprint.serve.plist")
OPENCODE = os.path.expanduser("~/.config/opencode")
MODEL = os.environ.get("FOOTPRINT_MODEL", "mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit")
CTX_BUDGET = 6000      # chars of history per training example
RESULT_CAP = 1500      # chars kept per tool result

SYSTEM = ("You are footprint, a local coding agent trained on Claude Code sessions. "
          "To act, emit tool calls as <tool name=\"NAME\">{json args}</tool>. "
          "Say DONE when the task is complete.")


def _text(content, cap=None):
    """Flatten a Claude message content (str or block list) to training text."""
    if isinstance(content, str):
        out = content
    else:
        parts = []
        for b in content or []:
            t = b.get("type")
            if t == "text":
                parts.append(b["text"])
            elif t == "tool_use":
                parts.append(f'<tool name="{b["name"]}">{json.dumps(b.get("input", {}))}</tool>')
            elif t == "tool_result":
                c = b.get("content")
                c = "".join(x.get("text", "") for x in c) if isinstance(c, list) else str(c or "")
                parts.append(f"<tool_result>{c[:RESULT_CAP]}</tool_result>")
        out = "\n".join(p for p in parts if p.strip())
    out = re.sub(r"<system-reminder>.*?</system-reminder>", "", out, flags=re.S)
    out = re.sub(r"<local-command-caveat>.*?</local-command-caveat>", "", out, flags=re.S)
    return (out[:cap] if cap else out).strip()


def parse_session(path):
    """One transcript file -> list of alternating {role, content} messages."""
    msgs = []
    for line in open(path, errors="replace"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") not in ("user", "assistant") or rec.get("isSidechain") or rec.get("isMeta"):
            continue
        m = rec.get("message") or {}
        role = m.get("role")
        txt = _text(m.get("content"))
        if not role or not txt:
            continue
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n" + txt
        else:
            msgs.append({"role": role, "content": txt})
    return msgs


def trace():
    """Arm tracing. Claude Code already logs every session to ~/.claude/projects;
    the marker makes collect use only sessions started after this moment."""
    os.makedirs(os.path.dirname(TRACE_MARK), exist_ok=True)
    with open(TRACE_MARK, "w") as f:
        f.write(str(time.time()))
    print("tracing armed. chat with Claude Code as usual — those sessions become training data.\n"
          "then: footprint.py collect && footprint.py train\n"
          "(delete ~/.claude/footprint-trace to collect ALL history again)")


def collect(project=None):
    since = float(open(TRACE_MARK).read()) if os.path.exists(TRACE_MARK) else 0.0
    slug = "-" + os.path.abspath(project or os.getcwd()).strip("/").replace("/", "-").replace(".", "-")
    dirs = [os.path.join(PROJECTS, slug)] if os.path.isdir(os.path.join(PROJECTS, slug)) \
        else glob.glob(os.path.join(PROJECTS, "*"))
    examples = []
    for d in dirs:
        for f in glob.glob(os.path.join(d, "*.jsonl")):
            if os.path.getmtime(f) < since:
                continue
            msgs = parse_session(f)
            # one example per assistant turn, with preceding context under budget
            for i, m in enumerate(msgs):
                if m["role"] != "assistant":
                    continue
                ctx, size = [], 0
                for prev in reversed(msgs[:i]):
                    size += len(prev["content"])
                    if size > CTX_BUDGET:
                        break
                    ctx.insert(0, prev)
                if not ctx or ctx[0]["role"] != "user":
                    continue
                examples.append({"messages": [{"role": "system", "content": SYSTEM}, *ctx, m]})
    if not examples:
        hint = " (trace marker active — only sessions after `trace` count; delete ~/.claude/footprint-trace for all history)" if since else ""
        sys.exit(f"no transcripts found under {PROJECTS}{hint}")
    random.seed(0)
    random.shuffle(examples)
    n_valid = max(1, len(examples) // 10)
    os.makedirs(DATA, exist_ok=True)
    for name, chunk in [("valid", examples[:n_valid]), ("train", examples[n_valid:])]:
        with open(os.path.join(DATA, f"{name}.jsonl"), "w") as fh:
            for e in chunk:
                fh.write(json.dumps(e) + "\n")
    print(f"collected {len(examples)} examples ({len(examples)-n_valid} train / {n_valid} valid) -> {DATA}")


def train():
    if not os.path.exists(os.path.join(DATA, "train.jsonl")):
        sys.exit("no data. run: footprint.py collect")
    subprocess.run([sys.executable, "-m", "mlx_lm", "lora", "--model", MODEL, "--train",
                    "--data", DATA, "--adapter-path", ADAPTERS,
                    "--iters", os.environ.get("FOOTPRINT_ITERS", "300"),
                    "--max-seq-length", "4096", "--batch-size", "1"], check=True)
    print(f"adapter saved -> {ADAPTERS}")


def serve():
    port = os.environ.get("FOOTPRINT_PORT", "8399")
    args = [sys.executable, "-m", "mlx_lm", "server", "--model", MODEL,
            "--host", "127.0.0.1", "--port", port]
    if os.path.exists(os.path.join(ADAPTERS, "adapters.safetensors")):
        args += ["--adapter-path", ADAPTERS]
    else:
        print("(no adapter yet — serving base model; run train first for footprint behavior)")
    print(f"OpenAI-compatible API: http://127.0.0.1:{port}/v1  (model name: footprint)\n"
          "point Cursor / OpenCode / Codex / any OpenAI-compatible client here, api key: none")
    subprocess.run(args, check=True)


def install():
    """Server runs itself (launchd, KeepAlive) + OpenCode /footprint command. User never runs serve."""
    if sys.platform != "darwin":
        sys.exit("install is macOS-only (launchd + MLX). on Linux/Windows run serve manually once MLX alternatives land.")
    py = os.path.join(ROOT, ".venv", "bin", "python")
    if not os.path.exists(py):
        sys.exit("no .venv. run: python3 footprint.py setup")
    port = os.environ.get("FOOTPRINT_PORT", "8399")
    os.makedirs(os.path.dirname(LAUNCHD), exist_ok=True)
    with open(LAUNCHD, "wb") as f:
        plistlib.dump({"Label": "com.footprint.serve",
                       "ProgramArguments": [py, os.path.join(ROOT, "footprint.py"), "serve"],
                       "RunAtLoad": True, "KeepAlive": True,
                       "StandardOutPath": "/tmp/footprint-serve.log",
                       "StandardErrorPath": "/tmp/footprint-serve.log"}, f)
    subprocess.run(["launchctl", "unload", LAUNCHD], capture_output=True)
    subprocess.run(["launchctl", "load", "-w", LAUNCHD], check=True)

    cfg_path = os.path.join(OPENCODE, "opencode.json")
    cfg = json.load(open(cfg_path)) if os.path.exists(cfg_path) else {"$schema": "https://opencode.ai/config.json"}
    cfg.setdefault("provider", {})["footprint"] = {
        "npm": "@ai-sdk/openai-compatible", "name": "footprint",
        "options": {"baseURL": f"http://127.0.0.1:{port}/v1"},
        "models": {"footprint": {"name": "footprint"}}}
    os.makedirs(os.path.join(OPENCODE, "command"), exist_ok=True)
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)
    with open(os.path.join(OPENCODE, "command", "footprint.md"), "w") as f:
        f.write("---\ndescription: do task with footprint — local model trained on your Claude sessions\n"
                "model: footprint/footprint\n---\n$ARGUMENTS\n")
    print(f"installed:\n"
          f"  server: launchd keeps http://127.0.0.1:{port}/v1 running (log: /tmp/footprint-serve.log)\n"
          f"  opencode: /footprint <task> uses it; or pick model 'footprint' via /models\n"
          f"  cursor/codex: base URL http://127.0.0.1:{port}/v1, any api key")


def status():
    tr = os.path.join(DATA, "train.jsonl")
    n = sum(1 for _ in open(tr)) if os.path.exists(tr) else 0
    print(f"model: {MODEL}\nexamples: {n}\nadapter: "
          f"{'yes' if os.path.exists(os.path.join(ADAPTERS, 'adapters.safetensors')) else 'no'}\n"
          f"tracing: {'armed since ' + time.ctime(float(open(TRACE_MARK).read())) if os.path.exists(TRACE_MARK) else 'off (collect uses all history)'}\n"
          f"server: {'launchd-managed' if os.path.exists(LAUNCHD) else 'not installed (run install)'}")


def setup():
    venv = os.path.join(ROOT, ".venv")
    if not os.path.exists(venv):
        subprocess.run([sys.executable, "-m", "venv", venv], check=True)
    if sys.platform == "darwin":
        subprocess.run([os.path.join(venv, "bin", "pip"), "install", "-q", "mlx-lm"], check=True)
    else:
        print("mlx-lm skipped (Apple Silicon only). trace/collect work here; "
              "copy data/ to a Mac for train/serve.")
    link = os.path.expanduser("~/.claude/skills/footprint")
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if not os.path.exists(link):
        os.symlink(os.path.join(ROOT, "skills", "footprint"), link)
    print(f"ready. /footprint skill linked -> {link}\nuse: {venv}/bin/python footprint.py collect|train|run")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"collect": lambda: collect(sys.argv[2] if len(sys.argv) > 2 else None),
     "trace": trace,
     "train": train,
     "serve": serve,
     "install": install,
     "status": status,
     "setup": setup}.get(cmd, lambda: sys.exit(__doc__))()
