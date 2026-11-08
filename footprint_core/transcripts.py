"""Parse Claude Code transcripts into training examples."""
import glob, json, os, random, re, sys

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


def project_dir(path):
    """~/.claude/projects/<slug> for a working dir. Claude Code maps every non-alphanumeric char to '-'."""
    return os.path.join(config.PROJECTS, re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path)))


def rejected(msgs):
    """Per message: True if it belongs to a task the user pushed back on — their next real
    prompt is a correction ("no, …", "still broken") or they interrupted it mid-way."""
    from .memory import is_correction
    prompts = [i for i, m in enumerate(msgs) if m["role"] == "user" and not m["content"].startswith("<tool_result>")]
    out = [False] * len(msgs)
    for a, b in zip(prompts, prompts[1:] + [len(msgs)]):
        bad = (b < len(msgs) and is_correction(msgs[b]["content"])) or \
            any("[Request interrupted" in m["content"] for m in msgs[a + 1:b] if m["role"] == "user")
        out[a:b] = [bad] * (b - a)
    return out


def collect(project=None):
    """Curated LoRA data: only turns the user accepted, secrets redacted, split by session
    in time order (oldest -> train, newer -> valid, newest -> test) so no session leaks across."""
    from .bench import holdout
    from .memory import _redact
    since = float(open(config.TRACE_MARK, encoding="utf-8").read()) if os.path.exists(config.TRACE_MARK) else 0.0
    pdir = project_dir(project or os.getcwd())
    dirs = [pdir] if os.path.isdir(pdir) else glob.glob(os.path.join(config.PROJECTS, "*"))
    held = holdout()
    sessions, seen, dupes, dropped = [], set(), 0, 0
    from .memory import ARCHIVE
    live = [f for d in dirs for f in glob.glob(os.path.join(d, "*.jsonl"))]
    names = {os.path.basename(f) for f in live}  # archived (redacted) copies stand in for sessions Claude Code deleted
    files = live + [a for d in dirs for a in glob.glob(os.path.join(ARCHIVE, os.path.basename(d), "*.jsonl"))
                    if os.path.basename(a) not in names]
    for d in [None]:
        for f in files:
            if os.path.getmtime(f) < since or os.path.basename(f)[:-6] in held:
                continue  # held-out bench sessions never become training data
            msgs = [{**m, "content": _redact(m["content"])} for m in parse_session(f)]
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
                ctx, size = [], 0
                for prev in reversed(msgs[:i]):
                    size += len(prev["content"])
                    if size > config.CTX_BUDGET:
                        break
                    ctx.insert(0, prev)
                if not ctx or ctx[0]["role"] != "user":
                    continue
                ex = {"messages": [{"role": "system", "content": config.SYSTEM}, *ctx, m]}
                sig = hash(json.dumps(ex["messages"], sort_keys=True))
                if sig in seen:
                    dupes += 1
                    continue
                seen.add(sig)
                examples.append(ex)
            if examples:
                sessions.append((os.path.getmtime(f), examples))
    if len(sessions) < 3:
        hint = " (trace marker active — only sessions after `trace` count; delete ~/.claude/footprint-trace for all history)" if since else ""
        sys.exit(f"need at least 3 sessions with accepted work under {config.PROJECTS}, found {len(sessions)}{hint}")
    sessions.sort(key=lambda s: s[0])
    k = max(1, len(sessions) // 10)
    splits = {"train": sessions[:-2 * k], "valid": sessions[-2 * k:-k], "test": sessions[-k:]}
    os.makedirs(config.DATA, exist_ok=True)
    counts = {}
    for name, chunk in splits.items():
        exs = [e for _, es in chunk for e in es]
        random.Random(0).shuffle(exs)  # shuffle within a split only: sessions never cross splits
        counts[name] = len(exs)
        with open(os.path.join(config.DATA, f"{name}.jsonl"), "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(e) + "\n" for e in exs)
    print(f"collected {sum(counts.values())} accepted examples from {len(sessions)} sessions "
          f"({counts['train']} train / {counts['valid']} valid / {counts['test']} test, split by session, newest = test)\n"
          f"  dropped {dropped} turns the user corrected or interrupted · {dupes} duplicates · secrets redacted\n"
          f"  -> {config.DATA}")
