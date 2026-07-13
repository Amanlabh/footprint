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


def collect(project=None):
    since = float(open(config.TRACE_MARK).read()) if os.path.exists(config.TRACE_MARK) else 0.0
    slug = "-" + os.path.abspath(project or os.getcwd()).strip("/").replace("/", "-").replace(".", "-")
    dirs = [os.path.join(config.PROJECTS, slug)] if os.path.isdir(os.path.join(config.PROJECTS, slug)) \
        else glob.glob(os.path.join(config.PROJECTS, "*"))
    examples, seen, dupes = [], set(), 0
    for d in dirs:
        for f in glob.glob(os.path.join(d, "*.jsonl")):
            if os.path.getmtime(f) < since:
                continue
            msgs = parse_session(f)
            if len(msgs) < 2:
                continue
            # one example per assistant turn, with preceding context under budget
            for i, m in enumerate(msgs):
                if m["role"] != "assistant":
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
    if not examples:
        hint = " (trace marker active — only sessions after `trace` count; delete ~/.claude/footprint-trace for all history)" if since else ""
        sys.exit(f"no transcripts found under {config.PROJECTS}{hint}")
    random.seed(0)
    random.shuffle(examples)
    n_valid = max(1, len(examples) // 10)
    os.makedirs(config.DATA, exist_ok=True)
    for name, chunk in [("valid", examples[:n_valid]), ("train", examples[n_valid:])]:
        with open(os.path.join(config.DATA, f"{name}.jsonl"), "w") as fh:
            for e in chunk:
                fh.write(json.dumps(e) + "\n")
    print(f"collected {len(examples)} examples ({len(examples)-n_valid} train / {n_valid} valid, "
          f"{dupes} duplicates skipped) -> {config.DATA}")
