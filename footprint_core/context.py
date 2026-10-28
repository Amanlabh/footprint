"""Session continuity: hand a new Claude Code session the state of the previous one.

Claude Code writes transcripts live, so "real-time" needs no daemon: at
SessionStart we read the newest other transcript in the project and print a
compact state (goal, files touched, open todos, last error, where it ended).
Hook stdout becomes context for the new session.
"""
import glob, json, os, sys, time

from . import config, transcripts

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _prompt(rec):
    """Real user prompt text, or None for tool results / meta / slash-command noise."""
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isSidechain"):
        return None
    c = (rec.get("message") or {}).get("content")
    if isinstance(c, list) and any(b.get("type") == "tool_result" for b in c):
        return None
    t = transcripts._text(c)
    return None if not t or t.startswith("<command-") else t


def state(path):
    """One transcript -> dict of what a successor session needs to know."""
    s = {"title": None, "prompts": [], "files": [], "todos": None, "error": None,
         "last": None, "branch": None, "cwd": None}
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") == "ai-title":
            s["title"] = rec.get("aiTitle")
        s["branch"] = rec.get("gitBranch") or s["branch"]
        s["cwd"] = rec.get("cwd") or s["cwd"]
        p = _prompt(rec)
        if p:
            s["prompts"].append(p)
        content = (rec.get("message") or {}).get("content")
        if rec.get("isSidechain") or not isinstance(content, list):
            continue
        for b in content:
            if b.get("type") == "tool_use":
                inp = b.get("input") or {}
                f = inp.get("file_path") or inp.get("notebook_path")
                if b.get("name") in EDIT_TOOLS and f:
                    if f in s["files"]:
                        s["files"].remove(f)
                    s["files"].append(f)  # most recent last
                elif b.get("name") == "TodoWrite":
                    s["todos"] = [t for t in inp.get("todos", []) if t.get("status") != "completed"]
            elif b.get("type") == "tool_result" and b.get("is_error"):
                s["error"] = transcripts._text([b], cap=400)
            elif b.get("type") == "text" and rec.get("type") == "assistant" and b["text"].strip():
                s["last"] = b["text"].strip()
    return s


def render(s, age_h):
    out = [f"# Previous session in this project (last active {age_h:.1f}h ago"
           + (f", branch {s['branch']}" if s["branch"] else "") + ")"]
    if s["title"]:
        out.append(f"Topic: {s['title']}")
    out.append(f"Goal (first ask): {s['prompts'][0][:600]}")
    if len(s["prompts"]) > 1:
        out.append("Latest asks:\n" + "\n".join(f"- {p[:300]}" for p in s["prompts"][-3:]))
    if s["files"]:
        out.append("Files touched: " + ", ".join(s["files"][-15:]))
    if s["todos"]:
        out.append("Open todos:\n" + "\n".join(f"- [{t.get('status')}] {t.get('content')}" for t in s["todos"]))
    if s["error"]:
        out.append(f"Last tool error (may be resolved): {s['error']}")
    if s["last"]:
        out.append(f"Where it ended:\n{s['last'][-800:]}")
    out.append("Continue from here if the user's next request relates; don't re-ask what's above.")
    return "\n\n".join(out)[:config.CONTEXT_CAP]


def previous(project_dir, current=None):
    """Newest transcript in project_dir that isn't the current session and has a real prompt."""
    for f in sorted(glob.glob(os.path.join(project_dir, "*.jsonl")), key=os.path.getmtime, reverse=True):
        if current and os.path.basename(f) == f"{current}.jsonl":
            continue
        age_h = (time.time() - os.path.getmtime(f)) / 3600
        if age_h > config.CONTEXT_MAX_AGE_H:
            return None  # sorted newest-first: everything after is staler
        s = state(f)
        if s["prompts"]:
            return s, age_h
    return None


def show(args=()):
    """`footprint context` — print previous-session state. As a SessionStart hook,
    reads the hook JSON from stdin; by hand, uses the current directory."""
    if args and args[0] == "install":
        return install()
    hook = {}
    if not sys.stdin.isatty():
        try:
            hook = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            pass
    tp = hook.get("transcript_path")
    pdir = os.path.dirname(tp) if tp else transcripts.project_dir(hook.get("cwd") or os.getcwd())
    found = previous(pdir, hook.get("session_id"))
    if found:
        print(render(*found))
    elif not hook:
        print(f"no previous session within {config.CONTEXT_MAX_AGE_H}h in {pdir}")


def install():
    """Register `footprint context` as a Claude Code SessionStart hook (startup + /clear)."""
    path = os.path.expanduser("~/.claude/settings.json")
    try:
        cfg = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    except json.JSONDecodeError:
        sys.exit(f"{path} is not valid JSON — fix it first, not overwriting")
    cmd = f'"{sys.executable}" "{config.ENTRY}" context'
    starts = cfg.setdefault("hooks", {}).setdefault("SessionStart", [])
    starts[:] = [e for e in starts if not any("footprint.py\" context" in h.get("command", "")
                                              for h in e.get("hooks", []))]
    starts.append({"matcher": "startup|clear", "hooks": [{"type": "command", "command": cmd}]})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    # ponytail: OpenCode gets a manual /continue (shell-output injection); auto needs an OpenCode plugin
    oc = os.path.join(config.OPENCODE, "commands", "continue.md")
    os.makedirs(os.path.dirname(oc), exist_ok=True)
    with open(oc, "w", encoding="utf-8") as f:
        f.write("---\ndescription: continue from your last Claude Code session in this project (footprint)\n---\n"
                f"!`{cmd}`\n\n$ARGUMENTS\n")
    print(f"continuity on: new Claude Code sessions start with the previous session's state.\n"
          f"  hook: SessionStart (startup|clear) in {path}\n"
          f"  opencode: /continue [task] in {oc}\n  preview: footprint context")


if __name__ == "__main__":  # self-check on a synthetic transcript
    import tempfile
    recs = [
        {"type": "ai-title", "aiTitle": "Fix login"},
        {"type": "user", "gitBranch": "main", "message": {"role": "user", "content": "fix the login bug"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/a.py"}},
            {"type": "tool_use", "name": "TodoWrite", "input": {"todos": [
                {"content": "add test", "status": "pending"}, {"content": "fix", "status": "completed"}]}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "is_error": True, "content": "boom"}]}},
        {"type": "user", "isMeta": True, "message": {"role": "user", "content": "meta noise"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "fixed, test next"}]}},
    ]
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "old.jsonl"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(map(json.dumps, recs)) + "\nnot json\n")
    open(os.path.join(d, "cur.jsonl"), "w").write("")
    os.utime(os.path.join(d, "old.jsonl"), (time.time() - 60,) * 2)
    s, age = previous(d, current="cur")
    assert s["prompts"] == ["fix the login bug"] and s["files"] == ["/a.py"], s
    assert s["todos"] == [{"content": "add test", "status": "pending"}] and "boom" in s["error"]
    txt = render(s, age)
    assert "Fix login" in txt and "fixed, test next" in txt and "branch main" in txt
    print("context state ok")
