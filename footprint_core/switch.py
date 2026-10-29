"""footprint switch: replay a Claude Code session as a real OpenCode session.

The full chat (prompts, replies, tool calls + results) is converted to
OpenCode's export format and loaded with `opencode import`, then opened with
`opencode -s <id>` — same conversation, continue typing in OpenCode.
"""
import glob, json, os, random, shutil, string, subprocess, sys, tempfile
from datetime import datetime

from . import config, context, transcripts

TOOLS = {"Bash": "bash", "Read": "read", "Edit": "edit", "MultiEdit": "edit", "Write": "write",
         "NotebookEdit": "edit", "Grep": "grep", "Glob": "glob", "WebFetch": "webfetch",
         "WebSearch": "websearch", "TodoWrite": "todowrite", "Task": "task", "Agent": "task"}
KEYS = {"file_path": "filePath", "notebook_path": "filePath", "old_string": "oldString",
        "new_string": "newString", "replace_all": "replaceAll"}
_B62 = string.digits + string.ascii_letters
_seq = [0]


def _id(prefix, ms, descending=False):
    """OpenCode-style id: 12 hex of (ms*4096 + counter) then 14 random base62.
    Sessions use the inverted (descending) form so newest sorts first."""
    _seq[0] += 1
    v = (int(ms) * 0x1000 + _seq[0]) & 0xFFFFFFFFFFFF
    if descending:
        v = ~v & 0xFFFFFFFFFFFF
    return f"{prefix}_{v:012x}" + "".join(random.choices(_B62, k=14))


def _ms(rec, last):
    try:
        ms = datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")).timestamp() * 1000
    except (KeyError, ValueError, AttributeError):
        ms = last
    return int(max(ms, last + 1))  # strictly increasing keeps ids and ordering sane


def _project_id(cwd):
    """OpenCode caches the project id in <git-common-dir>/opencode; fall back to root commit, then global."""
    git = lambda *a: subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True).stdout.strip()
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and os.path.exists(os.path.join(common, "opencode")):
        return open(os.path.join(common, "opencode"), encoding="utf-8").read().strip()
    root = git("rev-list", "--max-parents=0", "HEAD").splitlines()
    return root[0] if root else "global"


def _model():
    """User's OpenCode default model ("provider/model"), else Big Pickle."""
    try:
        m = json.load(open(os.path.join(config.OPENCODE, "opencode.json"), encoding="utf-8")).get("model")
    except (OSError, json.JSONDecodeError):
        m = None
    provider, _, model = (m or "opencode/big-pickle").partition("/")
    return provider, model


def convert(path, cwd):
    """Claude Code transcript -> OpenCode export dict ({info, messages})."""
    provider, model = _model()
    first = int(os.path.getmtime(path) * 1000)
    sid = _id("ses", first, descending=True)
    msgs, calls, ms, cur, user_id, title = [], {}, 0, None, None, None

    def part(msg, p):
        p.update(id=_id("prt", ms), sessionID=sid, messageID=msg["info"]["id"])
        msg["parts"].append(p)
        return p

    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") == "ai-title":
            title = rec.get("aiTitle")
        if rec.get("isSidechain") or rec.get("type") not in ("user", "assistant"):
            continue
        ms = _ms(rec, ms or first)
        prompt = context._prompt(rec)
        content = (rec.get("message") or {}).get("content")
        if prompt:
            cur = None
            user_id = _id("msg", ms)
            msg = {"info": {"id": user_id, "sessionID": sid, "role": "user", "time": {"created": ms},
                            "agent": "build", "model": {"providerID": provider, "modelID": model}}, "parts": []}
            part(msg, {"type": "text", "text": prompt})
            msgs.append(msg)
        elif rec.get("type") == "assistant" and isinstance(content, list) and user_id:
            if cur is None:
                cur = {"info": {"id": _id("msg", ms), "sessionID": sid, "role": "assistant", "parentID": user_id,
                                "mode": "build", "agent": "build", "path": {"cwd": cwd, "root": cwd}, "cost": 0,
                                "tokens": {"total": 0, "input": 0, "output": 0, "reasoning": 0,
                                           "cache": {"read": 0, "write": 0}},
                                "modelID": model, "providerID": provider,
                                "time": {"created": ms, "completed": ms}, "finish": "stop"}, "parts": []}
                msgs.append(cur)
            cur["info"]["time"]["completed"] = ms
            for b in content:
                if b.get("type") == "text" and b["text"].strip():
                    part(cur, {"type": "text", "text": b["text"], "time": {"start": ms, "end": ms}})
                elif b.get("type") == "tool_use":
                    inp = {KEYS.get(k, k): v for k, v in (b.get("input") or {}).items()}
                    calls[b.get("id")] = part(cur, {
                        "type": "tool", "tool": TOOLS.get(b["name"], b["name"].lower()), "callID": b.get("id"),
                        "state": {"status": "error", "input": inp, "error": "no result recorded",
                                  "time": {"start": ms, "end": ms}}})
        elif isinstance(content, list):  # tool results come back in user records
            for b in content:
                p = calls.get(b.get("tool_use_id")) if b.get("type") == "tool_result" else None
                if not p:
                    continue
                c = b.get("content")
                out = ("".join(x.get("text", "") for x in c if isinstance(x, dict)) if isinstance(c, list)
                       else str(c or ""))[:config.RESULT_CAP]
                st = p["state"]
                st["time"]["end"] = ms
                if b.get("is_error"):
                    st["error"] = out
                else:
                    st.pop("error", None)
                    st.update(status="completed", output=out, title=str(st["input"].get("command")
                              or st["input"].get("filePath") or st["input"].get("pattern") or p["tool"])[:80],
                              metadata={})
    if not msgs:
        return None
    title = title or msgs[0]["parts"][0]["text"][:60]
    info = {"id": sid, "slug": "from-claude", "projectID": _project_id(cwd), "directory": cwd,
            "title": f"{title} (from Claude Code)", "version": "footprint",
            "time": {"created": min(first, msgs[0]["info"]["time"]["created"]), "updated": ms}}
    return {"info": info, "messages": msgs}


def switch(args=()):
    """`footprint switch [claude-session-id]` — newest Claude session for this dir by default."""
    cwd = os.getcwd()
    pdir = transcripts.project_dir(cwd)
    files = sorted(glob.glob(os.path.join(pdir, "*.jsonl")), key=os.path.getmtime, reverse=True)
    if args:
        files = [f for f in files if os.path.basename(f).startswith(args[0])]
    path = next((f for f in files if context.state(f)["prompts"]), None)
    if not path:
        sys.exit(f"no Claude Code session found for {cwd}")
    data = convert(path, cwd)
    if not shutil.which("opencode"):
        sys.exit("opencode not found on PATH — install it first: https://opencode.ai")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
    r = subprocess.run(["opencode", "import", f.name], capture_output=True, text=True)
    os.unlink(f.name)
    if r.returncode:
        sys.exit(f"opencode import failed:\n{r.stderr or r.stdout}")
    sid = data["info"]["id"]
    n = len(data["messages"])
    print(f"imported '{data['info']['title']}' ({n} messages) into OpenCode as {sid}")
    if sys.stdout.isatty():
        os.execvp("opencode", ["opencode", "-s", sid])  # straight into the same chat
    print(f"open it: opencode -s {sid}")


if __name__ == "__main__":  # self-check: tool_use/result pairing + key/tool mapping
    recs = [
        {"type": "ai-title", "aiTitle": "Fix login"},
        {"type": "user", "timestamp": "2026-10-28T10:00:00Z", "message": {"role": "user", "content": "fix login"}},
        {"type": "assistant", "timestamp": "2026-10-28T10:00:01Z", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "looking"},
            {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": "/a.py", "old_string": "x", "new_string": "y"}},
            {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "pytest"}}]}},
        {"type": "user", "timestamp": "2026-10-28T10:00:02Z", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
            {"type": "tool_result", "tool_use_id": "t2", "is_error": True, "content": [{"type": "text", "text": "1 failed"}]}]}},
        {"type": "assistant", "timestamp": "2026-10-28T10:00:03Z", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "done"}]}},
        {"type": "user", "timestamp": "2026-10-28T10:00:04Z", "message": {"role": "user", "content": "thanks"}},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(map(json.dumps, recs)))
    d = convert(fh.name, "/tmp/proj")
    os.unlink(fh.name)
    roles = [m["info"]["role"] for m in d["messages"]]
    assert roles == ["user", "assistant", "user"], roles
    a = d["messages"][1]
    edit, bash = [p for p in a["parts"] if p["type"] == "tool"]
    assert edit["tool"] == "edit" and edit["state"]["status"] == "completed"
    assert edit["state"]["input"] == {"filePath": "/a.py", "oldString": "x", "newString": "y"}
    assert bash["state"]["status"] == "error" and bash["state"]["error"] == "1 failed"
    assert [p["text"] for p in a["parts"] if p["type"] == "text"] == ["looking", "done"]
    assert a["info"]["parentID"] == d["messages"][0]["info"]["id"]
    ids = [m["info"]["id"] for m in d["messages"]]
    assert ids == sorted(ids), ids  # ascending ids = chronological order
    assert d["info"]["title"] == "Fix login (from Claude Code)" and d["info"]["id"].startswith("ses_")
    print("switch convert ok")
