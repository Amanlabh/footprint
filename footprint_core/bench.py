"""Personal benchmark: how close does model X get to what Claude did, on *your* work?

Answer key = your own Claude Code sessions. A task qualifies when Claude ended
it with a git commit and ran a check (tsc / tests / lint / build) that passed.
Each candidate model gets the same prompt on a clean worktree of the commit
*before* Claude's, then the same check runs.

  footprint bench harvest [n]                      pick + validate held-out tasks (default 20)
  footprint bench run <provider/model>… [--memory on|off|both]
  footprint bench                                  show the latest report
  footprint bench upload                           send scores (numbers only) to your profile

Held-out sessions are excluded from memory and from `collect`, so no model can
copy the answer. Pass = check passes AND the model changed at least one file.
"""
import glob, json, os, re, shutil, subprocess, sys, tempfile, time

from . import config, context

HOME = os.path.expanduser("~/.footprint/bench")
TASKS = os.path.join(HOME, "tasks.json")
HOLDOUT = os.path.join(HOME, "holdout.txt")       # session ids kept out of memory + training
RESULTS = os.path.join(HOME, "results.json")
COMMIT = re.compile(r"\[[^\]\s]+(?: \(root-commit\))? ([0-9a-f]{7,40})\]"   # git commit output
                    r"|(?:^|<tool_result>)([0-9a-f]{7,12}) \S", re.M)         # or `git log --oneline` after -q
CHECK = re.compile(r"\b(npx tsc\b.*--noEmit|tsc --noEmit|(?:npm|pnpm|yarn|bun) (?:run )?(?:test|lint|build|typecheck)\b"
                   r"|(?:python3? -m |uvx )?pytest\b|go test\b|cargo (?:test|check|build)\b|next build\b|ruff check\b"
                   r"|node --check\b|(?:npx )?eslint\b|python3? -m (?!pip\b|venv\b|http\b|json\b)[\w.]+\s*$)")
# replaying these would touch the real world (remotes, prod, inboxes): never bench them
SIDE_EFFECT = re.compile(r"\b(push|deploy|publish|release|merge|send|e-?mail|notion|slack|login|vercel|npm i)\b", re.I)
NO_PUSH = {"GIT_CONFIG_COUNT": "3", "GIT_TERMINAL_PROMPT": "0",  # any push in a bench run hits a dead URL
           **{f"GIT_CONFIG_KEY_{i}": "url.blocked-by-footprint-bench://.pushInsteadOf" for i in range(3)},
           "GIT_CONFIG_VALUE_0": "https://", "GIT_CONFIG_VALUE_1": "git@", "GIT_CONFIG_VALUE_2": "ssh://"}
IMAGE = re.compile(r"\.(png|jpe?g|gif|webp)\b", re.I)
ACTIVE_S = 600                                    # sessions touched this recently are live: never hold them out
DEP_DIRS = ("node_modules", ".venv", "venv")      # ponytail: symlinked from the real repo; per-task installs if this proves flaky
RUN_TIMEOUT, CHECK_TIMEOUT = 900, 300


def holdout():
    return set(open(HOLDOUT).read().split()) if os.path.exists(HOLDOUT) else set()


def _git(cwd, *args):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)


def _check_cmd(command, cwd, root):
    """Pull the check segment out of a chained Claude command -> (subdir relative to repo root, cmd)."""
    here = cwd
    for seg in re.split(r"&&|;|\|\|", command):
        seg = seg.split("|")[0].replace("2>&1", "").strip()
        if seg.startswith("cd "):
            here = os.path.normpath(os.path.join(here, os.path.expanduser(seg[3:].strip().strip("'\""))))
        elif CHECK.search(seg):
            rel = os.path.relpath(here, root)
            return (None if rel.startswith("..") else rel), seg
    return None, None


def _tasks_in(path):
    """Claude transcript -> candidate tasks: prompt, cwd, commit hash, check command."""
    sid, out, cur, pending = os.path.basename(path)[:-6], [], None, {}
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        p = context._prompt(rec)
        if p:
            # earlier asks travel with the task, like footprint's handover would ("yes implement this")
            cur = {"sid": sid, "prompt": p, "cwd": rec.get("cwd"), "commit": None, "check": None, "files": [],
                   "t": _ts(rec), "history": [t["prompt"][:400] for t in out[-3:]]}
            out.append(cur)
            continue
        content = (rec.get("message") or {}).get("content")
        if not cur or rec.get("isSidechain") or not isinstance(content, list):
            continue
        for b in content:
            f = (b.get("input") or {}).get("file_path") if b.get("type") == "tool_use" else None
            if f and b.get("name") in context.EDIT_TOOLS and f not in cur["files"]:
                cur["files"].append(f)
            if b.get("type") == "tool_use" and b.get("name") == "Bash":
                pending[b.get("id")] = (cur, (b.get("input") or {}).get("command", ""))
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                task, cmd = pending.pop(b["tool_use_id"])
                text = context.transcripts._text([b])
                if "git commit" in cmd and (m := COMMIT.search(text)):
                    task["commit"] = m.group(1) or m.group(2)  # harvest verifies it exists in the repo
                if not b.get("is_error") and CHECK.search(cmd) and not task["check"]:
                    task["check"] = cmd  # same command may also commit: `tsc --noEmit && git commit`
    for t in out:  # committed in a later turn ("yes commit")? find it via git: first commit touching its files
        if not t["commit"] and t["files"] and t["t"] and t["cwd"] and os.path.isdir(t["cwd"]):
            hit = _git(t["cwd"], "log", f"--since=@{int(t['t'])}", f"--until=@{int(t['t']) + 172800}", "--reverse",
                       "--format=%h", "--", *t["files"]).stdout.split()
            t["commit"] = hit[0] if hit else None
    return [t for t in out if t["commit"] and t["cwd"]
            and not IMAGE.search(t["prompt"])  # a replayed model can't see the screenshot
            and not SIDE_EFFECT.search(t["prompt"])]


def _ts(rec):
    from datetime import datetime
    try:
        return datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError, AttributeError):
        return None


def _default_check(cwd, root):
    """No check in the session? Use the repo's own: typecheck script, tsc, pytest. -> (subdir, cmd) or (None, None)"""
    for d in dict.fromkeys([cwd, root]):  # task folder first, then repo root
        rel = os.path.relpath(d, root)
        try:
            scripts = json.load(open(os.path.join(d, "package.json"))).get("scripts") or {}
        except (OSError, ValueError):
            scripts = {}
        if "typecheck" in scripts:
            return rel, "npm run typecheck"
        if os.path.exists(os.path.join(d, "tsconfig.json")):
            return rel, "npx tsc --noEmit"
        if any(os.path.exists(os.path.join(d, f)) for f in ("pytest.ini", "conftest.py")) \
                or "[tool.pytest" in (open(os.path.join(d, "pyproject.toml")).read() if os.path.exists(os.path.join(d, "pyproject.toml")) else ""):
            return rel, "python3 -m pytest -q"
    return None, None


def _worktree(root, rev):
    """Isolated copy at `rev`: own .git (a worktree would write a model's commits/branches into the
    real repo's .git) and no remote, so nothing a model does can reach the real repo."""
    wt = tempfile.mkdtemp(prefix="fp-bench-")
    ok = subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", root, wt], capture_output=True).returncode == 0 \
        and _git(wt, "checkout", "-q", "--detach", rev).returncode == 0
    if not ok:
        shutil.rmtree(wt, ignore_errors=True)
        return None
    _git(wt, "remote", "remove", "origin")
    for d in DEP_DIRS:  # deps aren't in git; borrow the real repo's
        for src in glob.glob(os.path.join(root, d)) + glob.glob(os.path.join(root, "*", d)):
            dst = os.path.join(wt, os.path.relpath(src, root))
            if os.path.isdir(os.path.dirname(dst)) and not os.path.exists(dst):
                os.symlink(src, dst)
    return wt


def _drop(root, wt):
    shutil.rmtree(wt, ignore_errors=True)


def _run_check(wt, task):
    try:
        r = subprocess.run(task["check_cmd"], shell=True, cwd=os.path.join(wt, task["check_dir"]),
                           capture_output=True, timeout=CHECK_TIMEOUT)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def harvest(argv=()):
    """Newest qualifying tasks whose check really passes at Claude's commit -> held-out set."""
    n = int(argv[0]) if argv and argv[0].isdigit() else 20
    found, seen = [], set()
    from .memory import ARCHIVE
    live = glob.glob(os.path.join(config.PROJECTS, "*", "*.jsonl"))
    names = {os.path.basename(f) for f in live}  # plus archived copies of sessions Claude Code deleted
    files = sorted(live + [a for a in glob.glob(os.path.join(ARCHIVE, "*", "*.jsonl")) if os.path.basename(a) not in names],
                   key=os.path.getmtime, reverse=True)
    for f in files:
        if time.time() - os.path.getmtime(f) < ACTIVE_S:
            continue
        for t in _tasks_in(f):
            root = _git(t["cwd"], "rev-parse", "--show-toplevel").stdout.strip() if os.path.isdir(t["cwd"]) else ""
            if not root or t["commit"] in seen:
                continue
            parent = _git(root, "rev-parse", f"{t['commit']}^").stdout.strip()
            t["check_dir"], t["check_cmd"] = _check_cmd(t["check"], t["cwd"], root) if t["check"] else (None, None)
            if not t["check_cmd"]:
                t["check_dir"], t["check_cmd"] = _default_check(t["cwd"], root)
            if not parent or not t["check_cmd"]:
                continue
            t.update(root=root, parent=parent,
                     claude_files=_git(root, "diff", "--name-only", parent, t["commit"]).stdout.split())
            wt = _worktree(root, t["commit"])
            ok = wt and _run_check(wt, t)
            if wt:
                _drop(root, wt)
            if ok and t["claude_files"]:
                seen.add(t["commit"])
                found.append(t)
                print(f"  ✓ {os.path.basename(root)} {t['commit'][:7]}  {t['prompt'][:70]!r}")
            if len(found) >= n:
                break
        if len(found) >= n:
            break
    os.makedirs(HOME, exist_ok=True)
    json.dump(found, open(TASKS, "w"), indent=1)
    open(HOLDOUT, "w").write("\n".join(sorted({t["sid"] for t in found})) + "\n")
    print(f"{len(found)} held-out tasks -> {TASKS}\n(their sessions are now excluded from memory + collect)")
    if len(found) < 5:
        print("few tasks: the bench needs Claude sessions that ran a check and ended in a git commit")


def _prompt_for(t):
    if not t.get("history"):
        return t["prompt"]
    return ("Context — earlier asks in this session (already done):\n" + "\n".join(f"- {h}" for h in t["history"])
            + f"\n\nNow: {t['prompt']}")


def opencode_runner(model, prompt, wt, env):
    t = time.time()
    # OpenCode takes its project dir from $PWD, not the process cwd: an inherited PWD made it edit the
    # REAL repo. Pin both (verified live: edits land in the copy, session logged there).
    subprocess.run(["opencode", "run", "--dir", wt, "-m", model, prompt], cwd=wt, env={**env, "PWD": wt},
                   capture_output=True, timeout=RUN_TIMEOUT)
    return time.time() - t


def _tokens(wt):
    """Tokens OpenCode recorded for the session run in this worktree (0 if unknown)."""
    try:
        import sqlite3
        db = sqlite3.connect(f"file:{config.OPENCODE_DB}?mode=ro", uri=True)
        r = db.execute("select sum(tokens_input + tokens_output) from session where directory in (?, ?)",
                       (wt, os.path.realpath(wt))).fetchone()
        db.close()
        return int(r[0] or 0)
    except Exception:
        return 0


def run(argv, runner=opencode_runner):
    models = [a for a in argv if not a.startswith("--") and "/" in a]
    mode = next((a.split("=", 1)[1] for a in argv if a.startswith("--memory=")), "both")
    if not models:
        sys.exit("usage: footprint bench run <provider/model>… [--memory=on|off|both]")
    tasks = json.load(open(TASKS)) if os.path.exists(TASKS) else []
    if not tasks:
        sys.exit("no tasks. run: footprint bench harvest")
    rows = []
    for model in models:
        for mem in {"on": [True], "off": [False]}.get(mode, [False, True]):
            env = {**os.environ, **NO_PUSH, "FOOTPRINT_MEMORY": "on" if mem else "off"}
            passed, overlap, secs, toks = 0, 0.0, 0.0, 0
            for i, t in enumerate(tasks, 1):
                wt = _worktree(t["root"], t["parent"])
                if not wt:
                    continue
                try:
                    try:
                        secs += runner(model, _prompt_for(t), wt, env)
                    except subprocess.TimeoutExpired:
                        secs += RUN_TIMEOUT
                    changed = set(_git(wt, "diff", "--name-only", t["parent"]).stdout.split()) | {  # vs start: commits count
                        l[3:] for l in _git(wt, "status", "--porcelain").stdout.splitlines() if l.startswith("??")}
                    changed = {c for c in changed if os.path.basename(c.rstrip("/")) not in DEP_DIRS}
                    ok = bool(changed) and _run_check(wt, t)
                    ref = set(t["claude_files"])
                    overlap += len(changed & ref) / len(changed | ref) if changed | ref else 0
                    toks += _tokens(wt)
                    passed += ok
                    print(f"  [{model}{' +memory' if mem else ''}] {i}/{len(tasks)} {'PASS' if ok else 'fail'}  {t['prompt'][:60]!r}")
                finally:
                    _drop(t["root"], wt)
            n = len(tasks)
            rows.append({"model": model, "memory": mem, "passed": passed, "total": n,
                         "overlap": round(overlap / n, 3), "seconds": round(secs / n, 1), "tokens": toks // n})
    os.makedirs(HOME, exist_ok=True)
    hist = json.load(open(RESULTS)) if os.path.exists(RESULTS) else []
    hist.append({"date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tasks": len(tasks), "rows": rows})
    json.dump(hist, open(RESULTS, "w"), indent=1)
    report()


def report(_=()):
    hist = json.load(open(RESULTS)) if os.path.exists(RESULTS) else []
    if not hist:
        sys.exit("no results yet. run: footprint bench harvest, then footprint bench run <provider/model>")
    last = hist[-1]
    print(f"\nClaude parity — {last['tasks']} held-out tasks from your sessions · {last['date'][:10]}\n")
    print(f"{'model':<34}{'parity':>8}{'pass':>8}{'same files':>12}{'avg s':>8}{'tokens':>9}")
    print(f"{'Claude (reference)':<34}{'100%':>8}{last['tasks']:>5}/{last['tasks']:<2}{'100%':>12}")
    for r in sorted(last["rows"], key=lambda r: -r["passed"]):
        name = r["model"] + (" + memory" if r["memory"] else "")
        print(f"{name:<34}{r['passed'] * 100 // max(r['total'], 1):>7}%{r['passed']:>5}/{r['total']:<2}"
              f"{r['overlap'] * 100:>11.0f}%{r['seconds']:>8}{r['tokens']:>9}")


def upload(_=()):
    """Numbers only (model names, scores, counts, date) -> your profile. No prompts, code or diffs."""
    from . import vault
    hist = json.load(open(RESULTS)) if os.path.exists(RESULTS) else []
    if not hist:
        sys.exit("no results yet. run: footprint bench run <provider/model>")
    if not os.path.exists(vault.KEY_FILE):
        sys.exit("not signed in. run: footprint login fp_…")
    key = open(vault.KEY_FILE, encoding="utf-8").read().strip()
    code, r = vault._http(f"{vault.API}/api/bench", data=hist[-1], token=key)
    if code != 200:
        sys.exit(f"upload failed ({code}): {r.get('error', '')}")
    print(f"uploaded — see {vault.API}/account")


def main(argv):
    sub = argv[0] if argv else "report"
    {"harvest": harvest, "run": run, "report": report, "upload": upload}.get(
        sub, lambda _: sys.exit(__doc__))(argv[1:])


if __name__ == "__main__":  # self-check: real throwaway git repo + fake Claude transcript + fake model
    d = tempfile.mkdtemp()
    repo = os.path.join(d, "app")
    os.makedirs(repo)
    g = lambda *a: subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True)
    g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    open(os.path.join(repo, "m.py"), "w").write("def f():\n    return 1\n")
    g("add", "."); g("commit", "-qm", "base")
    open(os.path.join(repo, "m.py"), "w").write("def f():\n    return 2\n")
    g("commit", "-qam", "fix f")
    sha = _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    check = f'cd {repo} && python3 -c "import m; assert m.f() == 2" && echo ruff check ok'
    assert _check_cmd(check, "/elsewhere", repo)[0] == "." and "ruff check" in _check_cmd(check, "/x", repo)[1]
    proj = os.path.join(d, "projects", "p")
    os.makedirs(proj)
    rows = [{"type": "user", "cwd": repo, "message": {"role": "user", "content": "make f return 2"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "cd . && ruff check m.py"}},
                {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "git commit -am 'fix f'"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": "All checks passed!"},
                {"type": "tool_result", "tool_use_id": "b", "content": f"[main {sha}] fix f\n 1 file changed"}]}}]
    open(os.path.join(proj, "s1.jsonl"), "w").write("\n".join(json.dumps(r) for r in rows))
    os.utime(os.path.join(proj, "s1.jsonl"), (time.time() - 3600,) * 2)  # not a live session
    ts = _tasks_in(os.path.join(proj, "s1.jsonl"))
    assert ts[0]["history"] == [] and _prompt_for({"prompt": "go", "history": ["a"]}).endswith("Now: go")
    assert not IMAGE.search("make f return 2") and IMAGE.search("see '/var/x/Shot 1.PNG'")
    assert SIDE_EFFECT.search("create new branch commit and push") and not SIDE_EFFECT.search("make f return 2")
    assert CHECK.search("python3 -m footprint_core.memory") and not CHECK.search("python3 -m pip install x")
    blocked = subprocess.run(["git", "-C", repo, "push", "https://github.com/x/y.git", "HEAD:main"], env={**os.environ, **NO_PUSH},
                             capture_output=True, text=True)
    assert blocked.returncode and "blocked-by-footprint-bench" in blocked.stderr, blocked.stderr
    assert len(ts) == 1 and ts[0]["commit"] == sha and "ruff check" in ts[0]["check"], ts
    # harvest + run against the fake repo, with the check swapped for one python can verify
    config.PROJECTS, HOME = os.path.join(d, "projects"), os.path.join(d, "bench")
    from . import memory as _m
    _m.ARCHIVE = os.path.join(d, "archive")  # never the real archive
    TASKS, HOLDOUT, RESULTS = (os.path.join(HOME, x) for x in ("tasks.json", "holdout.txt", "results.json"))
    CHECK = re.compile(r"ruff check")
    _check_cmd = lambda c, cwd, root: (".", 'python3 -c "import m; assert m.f() == 2"')
    harvest(["5"])
    assert len(json.load(open(TASKS))) == 1 and holdout() == {"s1"}

    def fixer(model, prompt, wt, env):   # "good model": makes the fix
        open(os.path.join(wt, "m.py"), "w").write("def f():\n    return 2\n")
        subprocess.run(["git", "-C", wt, "commit", "-qam", "model fix"], capture_output=True)  # commits must count
        return 1.0

    def idler(model, prompt, wt, env):    # "bad model": touches nothing
        return 1.0
    run(["fake/good", "--memory=off"], runner=fixer)
    run(["fake/bad", "--memory=off"], runner=idler)
    h = json.load(open(RESULTS))
    assert h[0]["rows"][0]["passed"] == 1 and h[0]["rows"][0]["overlap"] == 1.0, h[0]
    assert h[1]["rows"][0]["passed"] == 0, h[1]
    iso = _worktree(repo, sha)  # isolation: own .git, no remotes, real repo untouched
    common = os.path.realpath(os.path.join(iso, _git(iso, "rev-parse", "--git-common-dir").stdout.strip()))
    assert common.startswith(os.path.realpath(iso)) and not _git(iso, "remote").stdout.strip(), common
    open(os.path.join(iso, "m.py"), "w").write("broken")
    assert open(os.path.join(repo, "m.py")).read() == "def f():\n    return 2\n"
    _drop(repo, iso)
    assert not os.path.exists(iso) and _git(repo, "worktree", "list").stdout.count("\n") == 1
    print("bench self-check ok")
