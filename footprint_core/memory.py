"""Session memory: any model gets "how you solved similar things before".

No training. Every past task (one real user prompt + what followed: files
edited, commands run, how it ended) from Claude Code and OpenCode goes into a
local index (~/.footprint/memory.json, rebuilt incrementally). On each new
prompt, `footprint recall` finds the closest past tasks (BM25, stdlib) and
prints a short brief that the Claude Code UserPromptSubmit hook / OpenCode
plugin adds to the conversation.

  footprint recall "add a year limit to the date picker"   # try it by hand
"""
import glob, hashlib, json, math, os, re, sqlite3, sys, time, urllib.request
from collections import Counter
from datetime import datetime

from . import bench, config, context, transcripts

INDEX = os.path.expanduser("~/.footprint/memory.json")
EMBEDS = os.path.expanduser("~/.footprint/embed.json")
ARCHIVE = os.path.expanduser("~/.footprint/archive")  # redacted copies: outlive Claude Code's transcript cleanup
ARCHIVE_IDLE = 1800   # seconds a transcript must sit unchanged before it's copied (don't rewrite the live one per prompt)
SHOWN = os.path.expanduser("~/.footprint/recall")  # per-session: task ids already injected
VERSION = 2           # 2: tasks carry "corrected" (the user's pushback on them)
TOP_K = 3
MIN_SCORE = 4.0       # ponytail: fixed BM25 cutoff; tune on real prompts or switch to embeddings if recall is weak
MIN_TERMS = 2         # need at least this many shared meaningful words
STOP = set("""a an and are as at be but by can do does for from get got has have how i if in into is it its
just let lets like make me my need no not now of on or our please so some that the then there this to
up us use using want was we what when where which why will with would you your yes ok okay also all any
should could thing things right file files code add fix
show list best possible suggest based help user users their them they one some any okay cool great tell
explain give know think way work working still really something new make made did done see look""".split())
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|fp_[A-Za-z0-9_-]{20,}"
                    r"|AKIA[0-9A-Z]{16}|xox[abpr]-[\w-]{10,}|eyJ[\w-]{20,}\.[\w-]{10,}\.[\w-]{10,}"
                    r"|(?i:(?:api[_-]?key|token|secret|password|passwd)\s*[=:]\s*)\S+"
                    # env-style: CMS_ADMIN_PASSWORD_HASH=…, GITHUB_CLIENT_SECRET=…, DATABASE_URL=…
                    r"|\b[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|PWD|API_?KEY|PRIVATE_KEY|CLIENT_ID|_KEY|DATABASE_URL|DSN)"
                    r"[A-Z0-9_]*\s*=\s*\S+"
                    r"|\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s]+@)")  # user:password@ in any URL


def _redact(t):
    return SECRET.sub("[redacted]", t or "")


# Pattern recognition shared by training (collect) and memory (facts / recall).
# ponytail: regex heuristics; an LLM classifier only if bench shows these labels are too noisy
CORRECTION = re.compile(r"^\W*(no\b|nope\b|wrong\b|undo\b|revert\b|stop\b|don'?t\b|do not\b|that'?s not\b|not what\b"
                        r"|why (did|are|is|would|didn'?t|didnt) (you|we|it|this)\b|why didn'?t\b|why didnt\b"
                        r"|you (broke|didn'?t|missed|forgot)\b|still\b|it'?s (not|broken|failing)\b"
                        r"|(it |this )?(doesn'?t|didn'?t|isn'?t) work"
                        r"|not working\b|this is wrong\b)|\[Request interrupted", re.I)
# standing-rule wording only; "instead of X" is almost always a one-off task instruction, not a habit
PREF = re.compile(r"\b(always|never|from now on|i prefer|prefer to|don'?t use|dont use|do not use|stop using)\b", re.I)
FACT_MIN = 2          # a preference must recur across tasks before it is injected: once = a task, twice = a pattern


def is_correction(t):
    """User pushed back on the previous answer (or interrupted it) -> that answer was rejected."""
    return bool(CORRECTION.search(t or ""))


TEMP_PATH = re.compile(r"'/(?:var|private|tmp)/[^']*'|/(?:var|private|tmp)/\S+")  # pasted screenshots etc.


def _words(t):
    # ponytail: plural-strip only; a real stemmer/embeddings if recall misses word forms
    t = TEMP_PATH.sub(" ", t or "")
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
            for w in re.findall(r"[a-z0-9_]{2,}", t.lower()) if w not in STOP]  # stop check before strip ("this")


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


def _link(tasks):
    """Attach the user's pushback to the task it was about, so memory says what NOT to repeat."""
    for a, b in zip(tasks, tasks[1:]):
        if is_correction(b["prompt"]):
            a["corrected"] = b["prompt"][:200]
    return tasks


def _redact_obj(o):
    """Redact every string inside parsed JSON: regex on the raw line could eat quotes and break the record."""
    if isinstance(o, str):
        return _redact(o)
    if isinstance(o, list):
        return [_redact_obj(x) for x in o]
    if isinstance(o, dict):
        return {k: _redact_obj(v) for k, v in o.items()}
    return o


def archive(files):
    """Redacted copy of each idle Claude transcript under ARCHIVE/<project>/<sid>.jsonl; recopied when it changes."""
    now = time.time()
    for f in files:
        m = os.path.getmtime(f)
        dst = os.path.join(ARCHIVE, os.path.basename(os.path.dirname(f)), os.path.basename(f))
        if now - m < ARCHIVE_IDLE or (os.path.exists(dst) and os.path.getmtime(dst) >= m):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(f, encoding="utf-8", errors="replace") as src, open(dst + ".tmp", "w", encoding="utf-8") as out:
            for line in src:
                try:
                    out.write(json.dumps(_redact_obj(json.loads(line))) + "\n")
                except json.JSONDecodeError:
                    pass
        os.replace(dst + ".tmp", dst)
        os.utime(dst, (m, m))  # same mtime as the source = up to date


def build(skip_sid=None):
    """Incremental index refresh: re-parse only sessions that changed since last time."""
    try:
        idx = json.load(open(INDEX, encoding="utf-8"))
        if idx.get("v") != VERSION:
            raise ValueError
    except (OSError, ValueError):
        idx = {"v": VERSION, "claude": {}, "opencode": {}}
    seen, held = set(), bench.holdout()  # bench answer key must never leak into memory
    live = glob.glob(os.path.join(config.PROJECTS, "*", "*.jsonl"))
    archive(live)
    names = {os.path.basename(f) for f in live}  # archived copies stand in only once Claude Code deleted the original
    for f in live + [a for a in glob.glob(os.path.join(ARCHIVE, "*", "*.jsonl")) if os.path.basename(a) not in names]:
        seen.add(f)
        m = os.path.getmtime(f)
        if os.path.basename(f) in (f"{skip_sid}.jsonl", *(f"{h}.jsonl" for h in held)):
            idx["claude"].pop(f, None)
            continue  # the live session (not "past" work) or a held-out bench session
        if idx["claude"].get(f, [0])[0] != m:
            idx["claude"][f] = [m, _link(_slim(claude_tasks(f)))]
    idx["claude"] = {f: v for f, v in idx["claude"].items() if f in seen}
    if os.path.exists(config.OPENCODE_DB):
        try:
            db = sqlite3.connect(f"file:{config.OPENCODE_DB}?mode=ro", uri=True)
            try:
                for sid, cwd, upd in db.execute("select id, directory, time_updated from session "
                                                "where parent_id is null and time_archived is null"):
                    if os.path.basename(cwd or "").startswith("fp-bench-"):
                        idx["opencode"].pop(sid, None)  # bench replays are tests, not your work
                        continue
                    if sid != skip_sid and idx["opencode"].get(sid, [0])[0] != upd:
                        idx["opencode"][sid] = [upd, _link(_slim(opencode_tasks(db, sid, cwd)))]
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
        if t.get("corrected"):
            lines.append("  user then corrected: " + t["corrected"].replace("\n", " "))
        out.append("\n".join(lines))
    return "\n".join(out)[:config.MEMORY_CAP]


# --- semantic recall: Ollama embeddings next to BM25 (finds "dob picker" for "birthday dropdown") ---
SIM_MIN = float(os.environ.get("FOOTPRINT_SIM_MIN", "0.65"))  # ponytail: fixed cosine cutoff for nomic-embed-text; retune per model
EMBED_BATCH = 32  # ponytail: hook backfills this many unembedded tasks per prompt; `recall --embed` does all at once


def _embed(texts):
    """Ollama /api/embed -> vectors, or None (Ollama down / model not pulled): recall stays BM25-only."""
    if os.environ.get("FOOTPRINT_EMBED") == "off" or not texts:
        return None
    req = urllib.request.Request(f"{config.OLLAMA_URL}/api/embed", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"model": config.EMBED_MODEL, "input": texts}).encode())
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)["embeddings"]
    except (OSError, ValueError, KeyError):
        return None


def _unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1
    return [round(x / n, 4) for x in v]


def embed_index(tasks, limit=EMBED_BATCH):
    """Load the vector cache, embed up to `limit` new tasks, drop vanished ones. -> {task id: unit vector}"""
    try:
        cache = json.load(open(EMBEDS, encoding="utf-8"))
        if cache.get("model") != config.EMBED_MODEL:
            raise ValueError
    except (OSError, ValueError):
        cache = {"model": config.EMBED_MODEL, "v": {}}
    ids = {t["id"] for t in tasks}
    todo = [t for t in tasks if t["id"] not in cache["v"]][:limit]
    changed = len(cache["v"]) != len(cache["v"].keys() & ids)
    cache["v"] = {k: v for k, v in cache["v"].items() if k in ids}
    for i in range(0, len(todo), EMBED_BATCH):
        part = todo[i:i + EMBED_BATCH]
        vecs = _embed([f"search_document: {t['prompt']} {' '.join(map(os.path.basename, t['files']))}" for t in part])
        if not vecs:
            break
        cache["v"].update((t["id"], _unit(v)) for t, v in zip(part, vecs))
        changed = True
    if changed:
        os.makedirs(os.path.dirname(EMBEDS), exist_ok=True)
        with open(EMBEDS + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        os.replace(EMBEDS + ".tmp", EMBEDS)
    return cache["v"]


def semantic(query, tasks, cwd=None, exclude_sid=None, exclude_ids=()):
    """Cosine over task embeddings; same-project nudge. -> [(score, task)], [] when embeddings are unavailable."""
    if len(_words(query)) < MIN_TERMS:
        return []
    q = _embed([f"search_query: {query}"])
    if not q:
        return []
    q, vecs = _unit(q[0]), embed_index(tasks)
    out = []
    for t in tasks:
        v = vecs.get(t["id"])
        if not v or t["sid"] == exclude_sid or t["id"] in exclude_ids:
            continue
        s = sum(a * b for a, b in zip(q, v))
        if cwd and t["cwd"] and os.path.abspath(cwd) == os.path.abspath(t["cwd"]):
            s += 0.03
        if s >= SIM_MIN:
            out.append((s, t))
    out.sort(key=lambda x: -x[0])
    return out[:TOP_K]


# --- habits (all projects) + project memory (this cwd): derived from the index, no LLM, no new store ---
MARKERS = {"package.json": "node", "pyproject.toml": "python", "requirements.txt": "python", "Cargo.toml": "rust",
           "go.mod": "go", "Gemfile": "ruby", "pom.xml": "java", "build.gradle": "java/kotlin", "Dockerfile": "docker",
           "next.config.js": "next.js", "next.config.ts": "next.js", "next.config.mjs": "next.js", "vercel.json": "vercel"}
TRIVIAL = set("cd echo ls cat head tail sed grep rg find wc sleep export rm mkdir cp mv true test pwd which "
              "for do done if then fi while break continue sort uniq awk tr xargs set source".split())


def _heads(cmd):
    """Program names a shell command runs: 'cd x && npm test | tail' -> ['npm']."""
    heads = []
    for seg in re.split(r"&&|\|\|?|;", cmd.split("\n")[0]):  # first line only: heredoc bodies aren't commands
        w = [x for x in seg.split() if "=" not in x[:1] and not re.match(r"^[A-Z_]+=", x)]
        if w and re.match(r"^[\w./-]+$", w[0]):
            h = os.path.basename(w[0])
            if h not in TRIVIAL:
                heads.append(h)
    return heads


def profile(tasks, cwd=None):
    """Session-start block: who you are as a developer + what this project is. '' when nothing learned."""
    here = [t for t in tasks if cwd and t["cwd"] and os.path.abspath(t["cwd"]) == os.path.abspath(cwd)]
    out = []  # standing preferences come from facts() (evidence-based), not from here
    tools = Counter(h for t in tasks for c in t["cmds"] for h in _heads(c)).most_common(8)
    exts = Counter(os.path.splitext(f)[1] for t in tasks for f in t["files"] if os.path.splitext(f)[1]).most_common(6)
    habits = []
    if tools:
        habits.append("tools you run: " + ", ".join(k for k, _ in tools))
    if exts:
        habits.append("you mostly edit: " + ", ".join(k for k, _ in exts))
    if habits:
        out.append("Habits: " + "; ".join(habits))
    if here:
        proj = [f"## This project: {os.path.basename(os.path.abspath(cwd))} ({len(here)} past tasks)"]
        stack = sorted({v for k, v in MARKERS.items() if os.path.exists(os.path.join(cwd, k))})
        if stack:
            proj.append("Stack: " + ", ".join(stack))
        root = os.path.abspath(cwd) + os.sep
        hot = Counter(f[len(root):] if f.startswith(root) else f for t in here for f in t["files"]).most_common(8)
        if hot:
            proj.append("Most-edited files: " + ", ".join(f for f, _ in hot))
        tools = Counter(h for t in here for c in t["cmds"] for h in _heads(c)).most_common(6)
        if tools:
            proj.append("Tools run here: " + ", ".join(k for k, _ in tools))
        now = time.time()
        recent = sorted(here, key=lambda t: -t["t"])[:5]
        proj.append("Recent work here:\n" + "\n".join(
            f"- {(now - t['t']) / 86400:.0f}d ago: {' '.join(t['prompt'].split())[:140]}" for t in recent))
        out.append("\n".join(proj))
    if not out:
        return ""
    head = "# Your profile (footprint — learned from your past sessions; follow unless the user says otherwise)"
    return "\n\n".join([head, *out])[:config.PROFILE_CAP]


def facts(tasks, cwd=None):
    """Structured memory (schema v1): standing preferences the user stated in their own prompts.
    Derived from the task index on demand, so nothing is stored twice or goes stale.
    Same word-set across sessions = one record with more evidence; newest wording wins;
    seen in 2+ projects = user scope, else project scope. cwd filters to user + that project."""
    recs = {}
    for t in tasks:
        for s in re.split(r"(?<=[.!?])\s+|\n", t["prompt"]):
            s = s.strip(" -*>\t")
            if not (12 <= len(s) <= 200 and PREF.search(s)) or s.startswith(("<", "{", '"')) \
                    or s.endswith("?") or '":' in s or re.search(r"never ?mind", s, re.I):
                continue
            key = " ".join(sorted(set(_words(s))))
            if not key:
                continue
            r = recs.setdefault(key, {"kind": "correction" if is_correction(t["prompt"]) else "preference",
                                      "text": s, "projects": set(), "evidence": [],
                                      "first": t["t"], "last": t["t"]})
            r["projects"].add(t["cwd"] or "?")
            r["evidence"].append(t["id"])
            r["first"] = min(r["first"], t["t"])
            if t["t"] >= r["last"]:
                r["text"], r["last"] = s, t["t"]
    here = os.path.abspath(cwd) if cwd else None
    day = lambda ts: datetime.fromtimestamp(ts).date().isoformat()
    out = []
    for key, r in recs.items():
        n, projs = len(r["evidence"]), sorted(r["projects"])
        scope = "user" if len(projs) > 1 else f"project:{projs[0]}"
        if here and scope not in ("user", f"project:{here}"):
            continue
        out.append({"id": "f_" + hashlib.sha1(key.encode()).hexdigest()[:8], "schema": 1, "kind": r["kind"],
                    "scope": scope, "text": r["text"], "count": n,
                    "confidence": round(min(0.95, 0.5 + 0.15 * (n - 1)), 2),  # ponytail: evidence-count prior
                    "evidence": r["evidence"][-5:], "first_seen": day(r["first"]), "last_seen": day(r["last"]),
                    "_last": r["last"]})
    out.sort(key=lambda r: (r["count"], r.pop("_last")), reverse=True)
    return out


def render_facts(recs, cap=1200):
    recs = [r for r in recs if r["count"] >= FACT_MIN][:12]
    if not recs:
        return ""
    lines = ["# Standing preferences (footprint memory — stated by this user in past sessions; "
             "follow unless told otherwise)"]
    lines += [f"- {r['text']}" + (f" (x{r['count']})" if r["count"] > 1 else "") for r in recs]
    return "\n".join(lines)[:cap]


def facts_cmd(args=()):
    """`footprint facts [--all]` — structured memory as JSON (this project + user-wide; --all = every project)."""
    print(json.dumps(facts(build(), None if "--all" in args else os.getcwd()), indent=2))


def recall(args=()):
    """`footprint recall` — hook mode reads {prompt, cwd, session_id} JSON on stdin
    (Claude UserPromptSubmit / OpenCode plugin); by hand: footprint recall <text>."""
    hook = {}
    if args == ["--embed"]:
        tasks = build()
        n = len(embed_index(tasks, limit=len(tasks)))
        return print(f"{n}/{len({t['id'] for t in tasks})} tasks embedded with {config.EMBED_MODEL}" if n else
                     f"no embeddings — is Ollama running? try: ollama pull {config.EMBED_MODEL}")
    if args:
        hook = {"prompt": " ".join(args), "cwd": os.getcwd()}
    elif not sys.stdin.isatty():
        try:
            hook = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            return
    prompt, sid = hook.get("prompt") or "", hook.get("session_id")
    if (os.environ.get("FOOTPRINT_MEMORY") == "off" or not prompt.strip() or context.HANDOFF_END in prompt
            or prompt.lstrip().startswith(context.NOISE)):  # harness messages (task notifications) aren't asks
        return
    shown_f = os.path.join(SHOWN, re.sub(r"[^\w-]", "_", sid)) if sid else None
    shown = set(open(shown_f).read().split()) if shown_f and os.path.exists(shown_f) else set()
    tasks = build(skip_sid=sid)
    hits = search(prompt, tasks, hook.get("cwd"), sid, shown)
    got = {t["id"] for _, t in hits}  # keyword hits first, then meaning-only matches BM25 missed
    hits = (hits + [h for h in semantic(prompt, tasks, hook.get("cwd"), sid, shown) if h[1]["id"] not in got])[:TOP_K]
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
    for leak, secret in (("APP_ADMIN_PASSWORD_HASH=deadbeef0000:1111", "deadbeef"),
                         ("APP_GITHUB_CLIENT_ID=FAKEclientid0000", "FAKEclient"), ("GITHUB_CLIENT_SECRET=abc123", "abc123"),
                         ("DATABASE_URL=postgresql://u:pw@host/db", "pw@"), ("STRIPE_SECRET_KEY=x9q8", "x9q8"),
                         ("see postgresql://user:hunter2@db.neon.tech/main", "hunter2")):
        assert "[redacted]" in _redact(leak) and secret not in _redact(leak), _redact(leak)
    assert _redact("PUBLIC_URL=http://localhost:3001 KEYBOARD layout") == "PUBLIC_URL=http://localhost:3001 KEYBOARD layout"
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
    shot = "'/var/folders/v_/x/T/TemporaryItems/NSIRD_screencaptureui_ab/Screenshot 2026-11-02 at 4.03.45 PM.png'"
    assert _words(shot) == [] and _words(f"fix this {shot} date picker") == ["date", "picker"]  # temp paths ignored
    assert not search("date picker years", ts + filler, exclude_sid="s1")  # current session excluded
    assert "dob-picker.tsx" in render(hits) and "asked:" in render(hits)
    pt = [_task("x", "a", "/p/app", 2, "fix the build"), _task("x", "b", "/o", 1, "add a footer")]
    pt[0]["files"], pt[0]["cmds"] = ["/p/app/src/a.ts", "/p/app/src/a.ts"], ["cd /p/app && pnpm test | tail -5", "pnpm test"]
    assert _heads("cd /p && FOO=1 pnpm test | tail -5; git push") == ["pnpm", "git"]
    assert _heads("python3 - <<'X'\nimport os\nX") == ["python3"]
    pr = profile(pt, "/p/app")
    assert pr.startswith("# Your profile") and "standing" not in pr.lower(), pr
    assert "tools you run: pnpm" in pr and "Tools run here: pnpm" in pr and "This project: app" in pr and "src/a.ts" in pr and ".ts" in pr, pr
    assert profile([], "/p/app") == ""
    vec = {"date picker years": [1, 0], "birthday dropdown range": [.9, .1], "billing": [0, 1]}
    _real, _embed = _embed, lambda xs: [vec.get(x.split(": ", 1)[1].split(" dob")[0].strip(), [0, 1]) for x in xs]
    EMBEDS = os.path.join(d, "embed.json")
    st = [_task("x", "s", "/p", 0, "date picker years")] + filler
    st[0]["files"] = []
    sem = semantic("birthday dropdown range", st)
    assert sem and sem[0][1] is st[0] and not search("birthday dropdown range", st), sem  # meaning, not words
    assert len(json.load(open(EMBEDS))["v"]) == len(st)  # cached
    _embed = lambda xs: None
    assert semantic("birthday dropdown range", st) == []  # Ollama down -> BM25 only
    assert is_correction("no, use pnpm not npm") and is_correction("still broken") and is_correction("[Request interrupted by user]")
    assert is_correction("why are we using local DB , use neon") and is_correction("still undfined")
    assert is_correction("why didnt mentioned continue command")
    assert not is_correction("now add a dark mode toggle") and not is_correction("notify the user on save")
    assert not is_correction("why do we need push notification ?")  # a question, not pushback
    lt = _link([_task("x", "s", "/p", 1, "add login"), _task("x", "s", "/p", 2, "no, use github oauth not email"),
                _task("x", "s", "/p", 3, "great, now tests")])
    assert lt[0]["corrected"].startswith("no, use github") and "corrected" not in lt[1]
    pf = [_task("x", "a", "/p1", 10, "Always use pnpm in this repo. Then add tests."),
          _task("x", "b", "/p2", 20, "always use pnpm in this repo!"),
          _task("x", "c", "/p1", 30, "never mind that, fix the header"),
          _task("x", "d", "/p3", 40, "don't use any for types")]
    fs = facts(pf)
    assert [f["text"] for f in fs] == ["always use pnpm in this repo!", "don't use any for types"], fs  # "never mind" skipped
    assert fs[0]["count"] == 2 and fs[0]["scope"] == "user" and fs[1]["scope"] == "project:/p3", fs
    assert [f["text"] for f in facts(pf, "/p1")] == ["always use pnpm in this repo!"]  # /p3 fact out of scope
    assert "pnpm" in render_facts(fs) and "any for types" not in render_facts(fs)  # seen once: not injected
    assert render_facts([]) == "" and not facts([_task("x", "e", "/p", 1, "should we always use pnpm?")])
    ARCHIVE, live_dir = os.path.join(d, "archive"), os.path.join(d, "proj")
    os.makedirs(live_dir)
    src = os.path.join(live_dir, "s9.jsonl")
    open(src, "w").write(json.dumps({"type": "user", "message": {"content": "export GITHUB_TOKEN=abc123 then deploy"}}) + "\nbad\n")
    os.utime(src, (time.time() - 4000,) * 2)
    archive([src])
    arc = os.path.join(ARCHIVE, "proj", "s9.jsonl")
    got = [json.loads(x) for x in open(arc)]
    assert len(got) == 1 and "abc123" not in got[0]["message"]["content"] and "deploy" in got[0]["message"]["content"], got
    assert os.path.getmtime(arc) == os.path.getmtime(src)
    print("memory self-check ok")
