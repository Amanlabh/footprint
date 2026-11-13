"""Parse Claude Code transcripts into training examples."""
import glob, json, os, random, re, subprocess, sys

from . import config


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
                parts.append(f"<tool_result>{c[:config.RESULT_CAP]}</tool_result>")
        out = "\n".join(p for p in parts if p.strip())
    out = re.sub(r"<system-reminder>.*?</system-reminder>", "", out, flags=re.S)
    out = re.sub(r"<local-command-caveat>.*?</local-command-caveat>", "", out, flags=re.S)
    return (out[:cap] if cap else out).strip()


def parse_session(path):
    """One transcript file -> list of alternating {role, content} messages."""
    msgs = []
    for line in open(path, encoding="utf-8", errors="replace"):
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


# Claude Code tool -> OpenCode tool (name, Claude arg -> OpenCode arg). Others (Task, MCP, Web…) have no
# OpenCode twin the model will be offered: their calls and results are dropped from training.
CC_TO_OC = {"Bash": ("bash", {"command": "command", "description": "description", "timeout": "timeout"}),
            "Read": ("read", {"file_path": "filePath", "offset": "offset", "limit": "limit"}),
            "Edit": ("edit", {"file_path": "filePath", "old_string": "oldString", "new_string": "newString",
                              "replace_all": "replaceAll"}),
            "Write": ("write", {"file_path": "filePath", "content": "content"}),
            "Grep": ("grep", {"pattern": "pattern", "path": "path", "glob": "include"}),
            "Glob": ("glob", {"pattern": "pattern", "path": "path"})}


def _clean(t):
    t = re.sub(r"<system-reminder>.*?</system-reminder>", "", t or "", flags=re.S)
    return re.sub(r"<local-command-caveat>.*?</local-command-caveat>", "", t, flags=re.S).strip()


def parse_native(path, errors=None):
    """Transcript -> chat messages in the model's native shape: assistant {content, tool_calls} with
    OpenCode tool names, role "tool" results. This is what the chat template renders at train time
    and what the model sees from OpenCode at run time.
    errors: optional set, filled with the ids of tool calls whose result came back as an error."""
    msgs, skip = [], set()
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("type") not in ("user", "assistant") or rec.get("isSidechain") or rec.get("isMeta"):
            continue
        content = (rec.get("message") or {}).get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else (content or [])
        if rec["type"] == "assistant":
            text, calls = [], []
            for b in blocks:
                if b.get("type") == "text" and b.get("text", "").strip():
                    text.append(b["text"].strip())
                elif b.get("type") == "tool_use":
                    name, amap = CC_TO_OC.get(b.get("name"), (None, None))
                    if not name:
                        skip.add(b.get("id"))
                        continue
                    args = {amap[k]: v for k, v in (b.get("input") or {}).items() if k in amap}
                    calls.append({"id": b.get("id"), "type": "function", "function": {"name": name, "arguments": args}})
            if not text and not calls:
                continue
            if msgs and msgs[-1]["role"] == "assistant":  # Claude streams one block per record: merge
                m = msgs[-1]
                m["content"] = "\n".join(x for x in (m["content"], *text) if x)
                if calls:
                    m.setdefault("tool_calls", []).extend(calls)
            else:
                msgs.append({"role": "assistant", "content": "\n".join(text), **({"tool_calls": calls} if calls else {})})
            continue
        for b in blocks:
            if b.get("type") == "tool_result":
                if b.get("tool_use_id") in skip:
                    continue
                if b.get("is_error") and errors is not None:
                    errors.add(b.get("tool_use_id"))
                c = b.get("content")
                c = "".join(x.get("text", "") for x in c) if isinstance(c, list) else str(c or "")
                msgs.append({"role": "tool", "tool_call_id": b.get("tool_use_id"), "content": _clean(c)[:config.RESULT_CAP]})
            elif b.get("type") == "text" and _clean(b.get("text")):
                t = _clean(b["text"])
                if msgs and msgs[-1]["role"] == "user":
                    msgs[-1]["content"] += "\n" + t
                else:
                    msgs.append({"role": "user", "content": t})
    return msgs


def project_dir(path):
    """~/.claude/projects/<slug> for a working dir. Claude Code maps every non-alphanumeric char to '-'."""
    return os.path.join(config.PROJECTS, re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path)))


def rejected(msgs):
    """Per message: True if it belongs to a task the user pushed back on — their next real
    prompt is a correction ("no, …", "still broken") or they interrupted it mid-way."""
    from .memory import is_correction
    prompts = [i for i, m in enumerate(msgs) if m["role"] == "user" and not m["content"].startswith("<tool_result>")]  # v1 text format too
    out = [False] * len(msgs)
    for a, b in zip(prompts, prompts[1:] + [len(msgs)]):
        bad = (b < len(msgs) and is_correction(msgs[b]["content"])) or \
            any("[Request interrupted" in m["content"] for m in msgs[a + 1:b] if m["role"] == "user")
        out[a:b] = [bad] * (b - a)
    return out


def split(sessions, keep_train=0.6):
    """Whole sessions, by time: newest -> test, next -> valid, rest -> train. Each eval split grows (one session
    at a time) until it holds max(MIN_EVAL, 10%) examples, as long as train keeps >= keep_train of all examples.
    Always at least one session each. sessions: [(time, [examples])]"""
    ss = sorted(sessions, key=lambda s: s[0])
    total = sum(len(e) for _, e in ss)
    want, floor = max(config.MIN_EVAL, -(-total // 10)), keep_train * total
    left, out = sum(len(e) for _, e in ss), {}
    for name in ("test", "valid"):
        got = []
        while len(ss) > 1 + (name == "test") and (not got or (sum(len(e) for _, e in got) < want
                                                                and left - len(ss[-1][1]) >= floor)):
            got.insert(0, ss.pop())
            left -= len(got[0][1])
        out[name] = got
    out["train"] = ss
    return {"train": out["train"], "valid": out["valid"], "test": out["test"]}


def collect(project=None):
    """Curated LoRA data: only turns the user accepted, secrets redacted, split by session
    in time order (oldest -> train, newer -> valid, newest -> test) so no session leaks across."""
    from .bench import holdout
    from .memory import _redact, _redact_obj
    since = float(open(config.TRACE_MARK, encoding="utf-8").read()) if os.path.exists(config.TRACE_MARK) else 0.0
    every = project == "--all"  # a model of you, not of one repo: all projects
    pdir = project_dir(os.getcwd() if every or not project else project)
    one = os.path.isdir(pdir) and not every
    dirs = [pdir] if one else glob.glob(os.path.join(config.PROJECTS, "*"))
    held = holdout()
    sessions, seen, dupes, dropped, botched = [], set(), 0, 0, 0
    from .memory import ARCHIVE
    live = [f for d in dirs for f in glob.glob(os.path.join(d, "*.jsonl"))]
    names = {os.path.basename(f) for f in live}  # archived (redacted) copies stand in for sessions Claude Code deleted
    files = live + [a for d in dirs for a in glob.glob(os.path.join(ARCHIVE, os.path.basename(d), "*.jsonl"))
                    if os.path.basename(a) not in names]
    for d in [None]:
        for f in files:
            if os.path.getmtime(f) < since or os.path.basename(f)[:-6] in held:
                continue  # held-out bench sessions never become training data
            errs = set()
            msgs = [_redact_obj(m) for m in parse_native(f, errs)]
            if len(msgs) < 2:
                continue
            bad, examples = rejected(msgs), []
            # one example per accepted assistant turn, with preceding context under budget
            for i, m in enumerate(msgs):
                if m["role"] != "assistant":
                    continue
                if bad[i]:
                    dropped += 1
                    continue
                if any(c["id"] in errs and c["function"]["name"] != "bash" for c in m.get("tool_calls", ())):
                    botched += 1  # a read/edit/write/grep the tool refused (file not read yet, text not found…)
                    continue      # is a mistake, not a habit. A failing shell command (tests!) is kept.
                if len(json.dumps(m)) > 4000:  # ~1.3k tokens of answer: with context it overflows 4096 and the
                    continue                   # truncation would cut the answer itself (big file writes)
                ctx, size = [], 0
                for prev in reversed(msgs[:i]):
                    size += len(json.dumps(prev))
                    if size > config.CTX_BUDGET:
                        break
                    ctx.insert(0, prev)
                while ctx and ctx[0]["role"] != "user":
                    ctx.pop(0)  # budget cut mid-turn: start at the nearest user message
                if not ctx:
                    continue
                ex = {"messages": [{"role": "system", "content": config.SYSTEM}, *ctx, m], "tools": config.TOOLS}
                sig = hash(json.dumps(ex["messages"], sort_keys=True))
                if sig in seen:
                    dupes += 1
                    continue
                seen.add(sig)
                examples.append(ex)
            if examples:
                sessions.append((os.path.getmtime(f), examples))
    # your own commits (no AI edit to those files in the 2 days before): best style signal there is
    from .memory import build, own_commits
    tasks = build()
    scope = [project or os.getcwd()] if one else sorted({t["cwd"] for t in tasks if t["cwd"]})
    roots = {}
    for c in scope:
        if os.path.isdir(c):
            r = subprocess.run(["git", "-C", c, "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
            if r:
                roots[r] = True
    mine, done = 0, set()
    for root in roots:
        for ts, h, subj in own_commits(tasks, root, days=365)[0]:
            if h in done:
                continue  # same repo via a worktree
            done.add(h)
            diff = subprocess.run(["git", "-C", root, "show", "--format=", "-U3", h], capture_output=True, text=True,
                                  errors="replace").stdout
            if not diff.strip() or len(diff) > config.CTX_BUDGET or "Binary files" in diff:
                continue
            msgs = [{"role": "system", "content": config.SYSTEM},
                    {"role": "user", "content": _redact(f"In {os.path.basename(root)}: {subj}\nWrite the change as a unified diff.")},
                    {"role": "assistant", "content": _redact(diff)}]
            sessions.append((ts, [{"messages": msgs, "tools": config.TOOLS}]))
            mine += 1
    if len(sessions) < 3:
        hint = " (trace marker active — only sessions after `trace` count; delete ~/.claude/footprint-trace for all history)" if since else ""
        sys.exit(f"need at least 3 sessions with accepted work under {config.PROJECTS}, found {len(sessions)}{hint}")
    splits = split(sessions)
    os.makedirs(config.DATA, exist_ok=True)
    counts = {}
    for name, chunk in splits.items():
        exs = [e for _, es in chunk for e in es]
        random.Random(0).shuffle(exs)  # shuffle within a split only: sessions never cross splits
        counts[name] = len(exs)
        with open(os.path.join(config.DATA, f"{name}.jsonl"), "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(e) + "\n" for e in exs)
    if counts["valid"] < config.MIN_EVAL:
        print(f"  note: only {counts['valid']} validation examples (<{config.MIN_EVAL}) — train will skip early stop. "
              "More sessions fix this.")
    print(f"collected {sum(counts.values())} accepted examples from {len(sessions)} sessions "
          f"({counts['train']} train / {counts['valid']} valid / {counts['test']} test, split by session, newest = test)\n"
          f"  includes {mine} of your own commits as diffs · dropped {dropped} turns the user corrected or interrupted"
          f" · {botched} refused tool calls · {dupes} duplicates · secrets redacted\n"
          f"  -> {config.DATA}")
