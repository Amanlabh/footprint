"""Session continuity: hand a new session the state of the previous one.

Works across tools: the previous session is the newest one for this project in
either Claude Code (~/.claude/projects/*.jsonl) or OpenCode (opencode.db).
Both write live, so "real-time" needs no daemon: at session start we read the
newest other session and print a compact state (goal, files touched, open
todos, last error, where it ended). Claude Code gets it via a SessionStart
hook, OpenCode via a plugin (plus /continue for existing sessions).
"""
import glob, json, os, sqlite3, sys, time

from . import config, transcripts

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "edit", "write"}
DONE = {"completed", "cancelled"}
HANDOFF_END = "Continue from here if the user's next request relates; don't re-ask what's above."
PLUGIN_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opencode_plugin.js")


def _new_state(src, **kw):
    return {"src": src, "title": None, "prompts": [], "files": [], "todos": None, "error": None,
            "last": None, "branch": None, "cwd": None, **kw}


def _touch(files, f):
    if f in files:
        files.remove(f)
    files.append(f)  # most recent last


def _strip_handoff(t):
    """Drop a footprint handoff block pasted in by /continue; keep the user's own words after it."""
    return t.split(HANDOFF_END, 1)[1].strip() if HANDOFF_END in t else t


def _prompt(rec):
    """Real user prompt text, or None for tool results / meta / slash-command noise."""
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isSidechain"):
        return None
    c = (rec.get("message") or {}).get("content")
    if isinstance(c, list) and any(b.get("type") == "tool_result" for b in c):
        return None
    t = _strip_handoff(transcripts._text(c))
    return None if not t or t.startswith("<command-") else t


def state(path):
    """One Claude Code transcript -> dict of what a successor session needs to know."""
    s = _new_state("Claude Code")
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
                    _touch(s["files"], f)
                elif b.get("name") == "TodoWrite":
                    s["todos"] = [t for t in inp.get("todos", []) if t.get("status") not in DONE]
            elif b.get("type") == "tool_result" and b.get("is_error"):
                s["error"] = transcripts._text([b], cap=400)
            elif b.get("type") == "text" and rec.get("type") == "assistant" and b["text"].strip():
                s["last"] = b["text"].strip()
    return s


def claude_previous(project_dir, current=None):
    """Newest Claude transcript in project_dir that isn't the current session and has a real prompt."""
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


def opencode_previous(cwd, current=None):
    """Newest top-level OpenCode session for cwd (not current) -> (state, age_h), or None."""
    if not os.path.exists(config.OPENCODE_DB):
        return None
    try:
        db = sqlite3.connect(f"file:{config.OPENCODE_DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        sessions = db.execute(
            "select id, title, time_updated from session where directory = ? and parent_id is null "
            "and time_archived is null and id != ? order by time_updated desc limit 5",
            (os.path.abspath(cwd), current or "")).fetchall()
        for sid, title, updated in sessions:
            age_h = (time.time() - updated / 1000) / 3600
            if age_h > config.CONTEXT_MAX_AGE_H:
                return None
            s = _new_state("OpenCode", title=title, cwd=cwd)
            roles = {mid: json.loads(d).get("role") for mid, d in
                     db.execute("select id, data from message where session_id = ?", (sid,))}
            for mid, d in db.execute("select message_id, data from part where session_id = ? "
                                     "order by time_created, id", (sid,)):
                p = json.loads(d)
                if p.get("type") == "text" and not p.get("synthetic") and (p.get("text") or "").strip():
                    if roles.get(mid) == "user":
                        t = _strip_handoff(p["text"].strip())
                        if t:
                            s["prompts"].append(t)
                    else:
                        s["last"] = p["text"].strip()
                elif p.get("type") == "tool":
                    st = p.get("state") or {}
                    f = (st.get("input") or {}).get("filePath")
                    if p.get("tool") in EDIT_TOOLS and f:
                        _touch(s["files"], f)
                    if st.get("status") == "error":
                        s["error"] = str(st.get("error") or "")[:400]
            s["todos"] = [{"content": c, "status": st} for c, st in db.execute(
                "select content, status from todo where session_id = ? order by position", (sid,))
                if st not in DONE]
            if s["prompts"]:
                return s, age_h
    except (sqlite3.Error, json.JSONDecodeError):
        return None  # OpenCode schema changed: degrade to Claude-only, never break the hook
    finally:
        db.close()
    return None


def previous(cwd, current=None, project_dir=None):
    """Newest prior session for this project across Claude Code and OpenCode."""
    found = [f for f in (claude_previous(project_dir or transcripts.project_dir(cwd), current),
                         opencode_previous(cwd, current)) if f]
    return min(found, key=lambda f: f[1]) if found else None


def render(s, age_h):
    out = [f"# Previous session in this project ({s['src']}, last active {age_h:.1f}h ago"
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
    out.append(HANDOFF_END)
    return "\n\n".join(out)[:config.CONTEXT_CAP]


def show(args=()):
    """`footprint context` — print previous-session state. As a hook (Claude
    SessionStart or the OpenCode plugin), reads {cwd, session_id, transcript_path?}
    JSON from stdin; by hand, uses the current directory."""
    if args and args[0] == "install":
        return install()
    hook = {}
    if not sys.stdin.isatty():
        try:
            hook = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            pass
    tp = hook.get("transcript_path")
    cwd = hook.get("cwd") or os.getcwd()
    found = previous(cwd, hook.get("session_id"), os.path.dirname(tp) if tp else None)
    if found:
        print(render(*found))
    elif not hook:
        print(f"no previous session within {config.CONTEXT_MAX_AGE_H}h for {cwd}")


def install():
    """Claude Code SessionStart hook + OpenCode plugin (auto) + /continue command (manual)."""
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
    plugin = os.path.join(config.OPENCODE, "plugins", "footprint.js")
    os.makedirs(os.path.dirname(plugin), exist_ok=True)
    src = open(PLUGIN_SRC, encoding="utf-8").read()
    with open(plugin, "w", encoding="utf-8") as f:
        f.write(src.replace("__PY__", json.dumps(sys.executable)).replace("__ENTRY__", json.dumps(config.ENTRY)))
    oc = os.path.join(config.OPENCODE, "commands", "continue.md")
    os.makedirs(os.path.dirname(oc), exist_ok=True)
    with open(oc, "w", encoding="utf-8") as f:
        f.write("---\ndescription: continue from your last session in this project, Claude Code or OpenCode (footprint)\n---\n"
                f"!`{cmd}`\n\n$ARGUMENTS\n")
    print(f"continuity on — new sessions start where the last one (Claude Code or OpenCode) left off.\n"
          f"  claude code: SessionStart hook (startup|clear) in {path}\n"
          f"  opencode:    auto via plugin {plugin}\n"
          f"               /continue [task] for sessions already open ({oc})\n"
          f"  preview:     footprint context")


if __name__ == "__main__":  # self-check on a synthetic Claude transcript + OpenCode db
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
    os.utime(os.path.join(d, "old.jsonl"), (time.time() - 3600,) * 2)
    s, age = claude_previous(d, current="cur")
    assert s["prompts"] == ["fix the login bug"] and s["files"] == ["/a.py"], s
    assert s["todos"] == [{"content": "add test", "status": "pending"}] and "boom" in s["error"]
    txt = render(s, age)
    assert "Fix login" in txt and "fixed, test next" in txt and "branch main" in txt and "Claude Code" in txt

    # OpenCode: newer session in same dir wins; handoff block stripped from its first prompt
    config.OPENCODE_DB = os.path.join(d, "opencode.db")
    db = sqlite3.connect(config.OPENCODE_DB)
    db.executescript("create table session (id, title, directory, parent_id, time_archived, time_updated);"
                     "create table message (id, session_id, data); create table part (id, message_id, session_id, time_created, data);"
                     "create table todo (session_id, content, status, position);")
    now = time.time() * 1000
    db.execute("insert into session values ('ses_1', 'Add OAuth', ?, null, null, ?)", (d, now - 60_000))
    db.execute("insert into session values ('ses_cur', 'current', ?, null, null, ?)", (d, now))
    db.executemany("insert into message values (?, 'ses_1', ?)", [("m1", '{"role":"user"}'), ("m2", '{"role":"assistant"}')])
    parts = [("m1", {"type": "text", "text": f"# Previous...\n\n{HANDOFF_END}\n\nadd github oauth"}),
             ("m1", {"type": "text", "text": "file dump", "synthetic": True}),
             ("m2", {"type": "tool", "tool": "edit", "state": {"status": "completed", "input": {"filePath": "/auth.ts"}}}),
             ("m2", {"type": "tool", "tool": "bash", "state": {"status": "error", "error": "npm ERR"}}),
             ("m2", {"type": "text", "text": "oauth wired, callback next"})]
    db.executemany("insert into part values (?, ?, 'ses_1', ?, ?)",
                   [(f"p{i}", m, i, json.dumps(p)) for i, (m, p) in enumerate(parts)])
    db.executemany("insert into todo values ('ses_1', ?, ?, ?)", [("callback route", "pending", 0), ("x", "cancelled", 1)])
    db.commit(); db.close()
    s, age = previous(d, current="ses_cur", project_dir=d)
    assert s["src"] == "OpenCode" and s["prompts"] == ["add github oauth"], s
    assert s["files"] == ["/auth.ts"] and s["error"] == "npm ERR" and s["last"] == "oauth wired, callback next"
    assert s["todos"] == [{"content": "callback route", "status": "pending"}]
    print("context state ok")
