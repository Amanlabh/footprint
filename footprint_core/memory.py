"""Session memory: any model gets "how you solved similar things before".

No training. Every past task (one real user prompt + what followed: files
edited, commands run, how it ended) from Claude Code and OpenCode goes into a
local index (~/.footprint/memory.json, rebuilt incrementally). On each new
prompt, `footprint recall` finds the closest past tasks (BM25, stdlib) and
prints a short brief that the Claude Code UserPromptSubmit hook / OpenCode
plugin adds to the conversation.

  footprint recall "add a year limit to the date picker"   # try it by hand
"""
import glob, json, math, os, re, sqlite3, sys, time
from datetime import datetime

from . import config, context, transcripts

INDEX = os.path.expanduser("~/.footprint/memory.json")
SHOWN = os.path.expanduser("~/.footprint/recall")  # per-session: task ids already injected
VERSION = 1
TOP_K = 3
MIN_SCORE = 4.0       # ponytail: fixed BM25 cutoff; tune on real prompts or switch to embeddings if recall is weak
MIN_TERMS = 2         # need at least this many shared meaningful words
STOP = set("""a an and are as at be but by can do does for from get got has have how i if in into is it its
just let lets like make me my need no not now of on or our please so some that the then there this to
up us use using want was we what when where which why will with would you your yes ok okay also all any
should could thing things right file files code add fix""".split())
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|fp_[A-Za-z0-9_-]{20,}"
                    r"|AKIA[0-9A-Z]{16}|xox[abpr]-[\w-]{10,}|eyJ[\w-]{20,}\.[\w-]{10,}\.[\w-]{10,}"
                    r"|(?i:(?:api[_-]?key|token|secret|password|passwd)\s*[=:]\s*)\S+)")


def _redact(t):
    return SECRET.sub("[redacted]", t or "")


def _words(t):
    # ponytail: plural-strip only; a real stemmer/embeddings if recall misses word forms
    ws = (w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
          for w in re.findall(r"[a-z0-9_]{2,}", (t or "").lower()))
    return [w for w in ws if w not in STOP]


def _task(src, sid, cwd, ts, prompt):
    return {"id": f"{sid}:{ts:.0f}", "src": src, "sid": sid, "cwd": cwd, "t": ts,
            "prompt": prompt, "files": [], "cmds": [], "outcome": None}


def _ts(rec, fallback):
    try:
        return datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError, AttributeError):
        return fallback


def claude_tasks(path):
    """One Claude Code transcript -> tasks (split at each real user prompt)."""
    sid, mtime = os.path.basename(path)[:-6], os.path.getmtime(path)
    tasks, cur, cwd = [], None, None
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        cwd = rec.get("cwd") or cwd
        p = context._prompt(rec)
        if p:
            cur = _task("Claude Code", sid, cwd, _ts(rec, mtime), p)
            tasks.append(cur)
            continue
        content = (rec.get("message") or {}).get("content")
        if not cur or rec.get("isSidechain") or not isinstance(content, list):
            continue
        for b in content:
            if b.get("type") == "tool_use":
                inp = b.get("input") or {}
                f = inp.get("file_path") or inp.get("notebook_path")
                if b.get("name") in context.EDIT_TOOLS and f:
                    context._touch(cur["files"], f)
                elif b.get("name") == "Bash" and inp.get("command"):
                    cur["cmds"].append(inp["command"])
            elif b.get("type") == "text" and rec.get("type") == "assistant" and b["text"].strip():
                cur["outcome"] = b["text"].strip()
    return tasks


def opencode_tasks(db, sid, cwd):
    """One OpenCode session -> tasks."""
    roles = {mid: json.loads(d).get("role") for mid, d in
             db.execute("select id, data from message where session_id = ?", (sid,))}
    tasks, cur = [], None
    for mid, created, d in db.execute("select message_id, time_created, data from part where session_id = ? "
                                      "order by time_created, id", (sid,)):
        p = json.loads(d)
        if p.get("type") == "text" and not p.get("synthetic") and (p.get("text") or "").strip():
            if roles.get(mid) == "user":
                t = context._strip_handoff(p["text"].strip())
                if t:
                    cur = _task("OpenCode", sid, cwd, created / 1000, t)
                    tasks.append(cur)
            elif cur:
                cur["outcome"] = p["text"].strip()
        elif p.get("type") == "tool" and cur:
            inp = (p.get("state") or {}).get("input") or {}
            if p.get("tool") in context.EDIT_TOOLS and inp.get("filePath"):
                context._touch(cur["files"], inp["filePath"])
            elif p.get("tool") == "bash" and inp.get("command"):
                cur["cmds"].append(inp["command"])
    return tasks


def _slim(tasks):
    """Keep the index small and secret-free."""
    for t in tasks:
        t["prompt"] = _redact(t["prompt"][:600])
        t["files"] = t["files"][-8:]
        t["cmds"] = [_redact(c[:160]) for c in t["cmds"][-4:]]
        t["outcome"] = _redact((t["outcome"] or "")[-400:]) or None
    return tasks


def build(skip_sid=None):
    """Incremental index refresh: re-parse only sessions that changed since last time."""
    try:
        idx = json.load(open(INDEX, encoding="utf-8"))
        if idx.get("v") != VERSION:
            raise ValueError
    except (OSError, ValueError):
        idx = {"v": VERSION, "claude": {}, "opencode": {}}
    seen = set()
    for f in glob.glob(os.path.join(config.PROJECTS, "*", "*.jsonl")):
        seen.add(f)
        m = os.path.getmtime(f)
        if os.path.basename(f) == f"{skip_sid}.jsonl":
            continue  # the live session: its own tasks aren't "past" work
        if idx["claude"].get(f, [0])[0] != m:
            idx["claude"][f] = [m, _slim(claude_tasks(f))]
    idx["claude"] = {f: v for f, v in idx["claude"].items() if f in seen}
    if os.path.exists(config.OPENCODE_DB):
        try:
            db = sqlite3.connect(f"file:{config.OPENCODE_DB}?mode=ro", uri=True)
            try:
                for sid, cwd, upd in db.execute("select id, directory, time_updated from session "
                                                "where parent_id is null and time_archived is null"):
                    if sid != skip_sid and idx["opencode"].get(sid, [0])[0] != upd:
                        idx["opencode"][sid] = [upd, _slim(opencode_tasks(db, sid, cwd))]
            finally:
                db.close()
        except (sqlite3.Error, json.JSONDecodeError):
            pass  # OpenCode schema changed: Claude-only memory, never break the hook
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(idx, fh)
    os.replace(tmp, INDEX)
    return [t for _, ts in (*idx["claude"].values(), *idx["opencode"].values()) for t in ts]


def search(query, tasks, cwd=None, exclude_sid=None, exclude_ids=()):
    """BM25 over prompt (+ file names, outcome); same-project boost. -> [(score, task)]"""
    q = set(_words(query))
    if len(q) < MIN_TERMS:
        return []
    docs = []  # (task, key words = prompt + file names: what it was *about*, all words incl. outcome)
    for t in tasks:
        if t["sid"] == exclude_sid or t["id"] in exclude_ids:
            continue
        kw = _words(f"{t['prompt']} {' '.join(map(os.path.basename, t['files']))}")
        docs.append((t, kw, kw + kw + _words(t["outcome"])))
    if not docs:
        return []
    n, avg = len(docs), sum(len(w) for *_, w in docs) / len(docs) or 1
    df = {}
    for *_, ws in docs:
        for w in set(ws) & q:
            df[w] = df.get(w, 0) + 1
    out = []
    for t, kw, ws in docs:
        if len(q & set(kw)) < MIN_TERMS:  # outcome alone can't qualify a task (e.g. SQL "LIMIT")
            continue
        shared = q & set(ws)
        tf = {w: ws.count(w) for w in shared}
        s = sum(math.log(1 + (n - df[w] + .5) / (df[w] + .5)) * tf[w] * 2.2 / (tf[w] + 1.2 * (.25 + .75 * len(ws) / avg))
                for w in shared)
        if cwd and t["cwd"] and os.path.abspath(cwd) == os.path.abspath(t["cwd"]):
            s *= 1.5
        if s >= MIN_SCORE:
            out.append((s, t))
    out.sort(key=lambda x: -x[0])
    return [h for h in out[:TOP_K] if h[0] >= out[0][0] * 0.5]  # weak tail = noise


def render(hits):
    now, out = time.time(), ["# Similar past work (footprint memory — how this user solved related tasks before; "
                             "reuse what fits, verify before relying on it)"]
    for _, t in hits:
        days = (now - t["t"]) / 86400
        when = f"{days:.0f}d ago" if days >= 1 else f"{days * 24:.0f}h ago"
        proj = os.path.basename(t["cwd"] or "") or "?"
        lines = [f"- [{proj} · {t['src']} · {when}] asked: {t['prompt'][:300]}"]
        if t["files"]:
            lines.append("  files: " + ", ".join(t["files"][-6:]))
        if t["cmds"]:
            lines.append("  ran: " + " | ".join(t["cmds"][-3:]))
        if t["outcome"]:
            lines.append("  ended: " + t["outcome"][-300:].replace("\n", " "))
        out.append("\n".join(lines))
    return "\n".join(out)[:config.MEMORY_CAP]


def recall(args=()):
    """`footprint recall` — hook mode reads {prompt, cwd, session_id} JSON on stdin
    (Claude UserPromptSubmit / OpenCode plugin); by hand: footprint recall <text>."""
    hook = {}
    if args:
        hook = {"prompt": " ".join(args), "cwd": os.getcwd()}
    elif not sys.stdin.isatty():
        try:
            hook = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            return
    prompt, sid = hook.get("prompt") or "", hook.get("session_id")
    if not prompt.strip() or context.HANDOFF_END in prompt:
        return
    shown_f = os.path.join(SHOWN, re.sub(r"[^\w-]", "_", sid)) if sid else None
    shown = set(open(shown_f).read().split()) if shown_f and os.path.exists(shown_f) else set()
    hits = search(prompt, build(skip_sid=sid), hook.get("cwd"), sid, shown)
    if not hits:
        if args:
            print("no similar past work found")
        return
    print(render(hits))
    if shown_f:  # don't repeat the same memory every prompt in one session
        os.makedirs(SHOWN, exist_ok=True)
        with open(shown_f, "a") as fh:
            fh.write("".join(f"{t['id']}\n" for _, t in hits))


if __name__ == "__main__":  # self-check: redaction, task split, ranking, threshold
    assert "[redacted]" in _redact("export OPENAI_API_KEY=sk-abcdefghijklmnopqrstu") and "sk-" not in _redact("sk-abcdefghijklmnopqrstuvwx")
    assert _redact("token: hunter2") == "[redacted]" and _redact("plain text") == "plain text"
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "s1.jsonl")
    rows = [{"type": "user", "cwd": "/p/app", "timestamp": "2026-10-01T10:00:00Z",
             "message": {"role": "user", "content": "limit the date picker dropdown years to 2005-2012"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "/p/app/dob-picker.tsx"}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "npm test -- dob"}},
                {"type": "text", "text": "Set fromYear=2005 toYear=2012."}]}},
            {"type": "user", "cwd": "/p/app", "timestamp": "2026-10-01T11:00:00Z",
             "message": {"role": "user", "content": "deploy the landing page to vercel production"}}]
    open(p, "w").write("\n".join(json.dumps(r) for r in rows))
    ts = _slim(claude_tasks(p))
    assert len(ts) == 2 and ts[0]["files"] == ["/p/app/dob-picker.tsx"] and ts[0]["cmds"] == ["npm test -- dob"], ts
    assert ts[0]["outcome"] == "Set fromYear=2005 toYear=2012." and ts[1]["outcome"] is None
    filler = [_task("x", f"f{i}", "/o", 0, f"unrelated chore number {i} about billing emails") for i in range(30)]
    hits = search("change the year range in the date picker", ts + filler, "/p/app")
    assert hits and hits[0][1]["prompt"].startswith("limit the date picker"), hits
    assert not search("ok push it", ts + filler)                       # too few meaningful words
    assert not search("date picker years", ts + filler, exclude_sid="s1")  # current session excluded
    assert "dob-picker.tsx" in render(hits) and "asked:" in render(hits)
    print("memory self-check ok")
