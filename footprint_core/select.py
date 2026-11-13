"""Pick the lessons that teach the most, so training time stops growing with every session.

A lesson = chat so far + the answer Claude gave. Most are repeats ("run a shell command" 200 times) or
things the base model already does. Pipeline, on the TRAIN split only (valid/test stay as collected):

  1. quality    drop answers with nothing in them
  2. near-copy  same ask + same answer up to numbers/paths/hashes (Jaccard on word 3-grams)
  3. surprise   how wrong the UNTRAINED model is on the answer (its loss). Already right = nothing to learn
  4. spread     greedy pick of `k` lessons: each next one = most surprising AND least like those already picked

Steps 1, 2, 4 are stdlib. Step 3 needs the model (backends/mlx_score.py); without scores every lesson
counts the same and the pick is spread only.

ponytail: similarity is TF-IDF on words (tool name, command, text). Swap for embeddings if lessons that
mean the same but share no words start slipping through.
"""
import hashlib, json, math, re
from collections import Counter

NEAR = 0.85     # Jaccard of word 3-grams above this = a near-copy
CLIP = 0.95     # surprise is clipped at this percentile: one giant file write must not outweigh everything


def lesson_id(e):
    return hashlib.sha1(json.dumps(e["messages"], sort_keys=True).encode()).hexdigest()[:16]


def _answer(e):
    a = e["messages"][-1]
    calls = " ".join(f"{c['function']['name']} {json.dumps(c['function'].get('arguments', {}), sort_keys=True)}"
                     for c in a.get("tool_calls") or ())
    return f"{a.get('content') or ''} {calls}".strip()


def key_text(e):
    """What the lesson teaches: the message it answers (its tail) + the answer."""
    prev = e["messages"][-2] if len(e["messages"]) > 1 else {}
    return f"{str(prev.get('content') or '')[-400:]} {_answer(e)}"


def _words(t):
    t = re.sub(r"\b[0-9a-f]{7,40}\b", " H ", t.lower())   # commit hashes, ids
    t = re.sub(r"\d+", "0", t)                             # numbers
    return re.findall(r"[a-z_][a-z0-9_]*|0", t)


def _grams(t):
    w = _words(t)
    return {" ".join(w[i:i + 3]) for i in range(max(1, len(w) - 2))}


def quality(e):
    """Reason this lesson can't teach anything, or None."""
    a = e["messages"][-1]
    if not (a.get("content") or "").strip() and not a.get("tool_calls"):
        return "empty answer"
    if not a.get("tool_calls") and len(_words(a.get("content") or "")) < 3:
        return "one-word answer"
    return None


def dedupe(rows):
    """Drop near-copies, keeping the first of each. -> (kept, dropped count)"""
    kept, grams = [], []
    for e in rows:
        g = _grams(key_text(e))
        if any(len(g & h) / (len(g | h) or 1) >= NEAR for h in grams):
            continue
        kept.append(e)
        grams.append(g)
    return kept, len(rows) - len(kept)


def _vectors(rows):
    docs = [Counter(_words(key_text(e))) for e in rows]
    df = Counter(w for d in docs for w in d)
    n, out = len(docs), []
    for d in docs:
        v = {w: (1 + math.log(c)) * math.log(1 + n / df[w]) for w, c in d.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        out.append({w: x / norm for w, x in v.items()})
    return out


def _cos(a, b):
    if len(b) < len(a):
        a, b = b, a
    return sum(x * b.get(w, 0) for w, x in a.items())


def pick(rows, k, scores=None):
    """Greedy: next = argmax surprise x (1 - similarity to the closest lesson already picked)."""
    if len(rows) <= k:
        return list(rows)
    w = [1.0] * len(rows)
    if scores:
        s = [scores.get(lesson_id(e)) for e in rows]
        known = sorted(x for x in s if x is not None)
        if known:
            top = known[min(len(known) - 1, int(CLIP * len(known)))] or 1
            mid = known[len(known) // 2]
            w = [max(0.05, min(x if x is not None else mid, top) / top) for x in s]
    vecs, far = _vectors(rows), [1.0] * len(rows)   # far[i] = 1 - max similarity to anything picked
    left, out = set(range(len(rows))), []
    while left and len(out) < k:
        i = max(left, key=lambda j: (w[j] * far[j], -j))
        left.discard(i)
        out.append(i)
        for j in left:
            far[j] = min(far[j], 1 - _cos(vecs[i], vecs[j]))
    return [rows[i] for i in sorted(out)]


def select(rows, k, scores=None):
    """-> (picked lessons, report). scores: {lesson_id: base-model loss on the answer} or None."""
    rep = {"start": len(rows)}
    good = [e for e in rows if not quality(e)]
    rep["low_quality"] = len(rows) - len(good)
    good, rep["near_copies"] = dedupe(good)
    out = pick(good, k, scores)
    rep.update(not_picked=len(good) - len(out), kept=len(out), scored=bool(scores))
    return out, rep


def needs_scores(rows, k):
    """Scoring costs a model pass per lesson: only worth it when there is something to cut."""
    good, _ = dedupe([e for e in rows if not quality(e)])
    return good if len(good) > k else []


def describe(rep):
    return (f"{rep['start']} lessons -> {rep['kept']} picked: {rep['low_quality']} empty, {rep['near_copies']} near-copies, "
            f"{rep['not_picked']} " + ("already known to the model or repeats of a picked one" if rep["scored"]
                                       else "repeats of a picked one (no surprise scores)"))


if __name__ == "__main__":  # self-check
    L = lambda ask, text="", **call: {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": ask},
                                                    {"role": "assistant", "content": text, **({"tool_calls": [
                                                        {"id": "x", "function": {"name": "bash", "arguments": call}}]} if call else {})}]}
    a = L("run the tests", command="npm test -- auth 12")
    b = L("run the tests", command="npm test -- auth 47")           # same up to a number
    c = L("add a dark mode toggle to the settings page", "Added the toggle in settings.tsx and wired the theme context.")
    d = L("why is the build failing on ci", "The lockfile is out of date, so the install step fails.")
    assert quality(L("x")) == "empty answer" and quality(L("x", "ok")) == "one-word answer" and not quality(a) and not quality(c)
    kept, n = dedupe([a, b, c, d])
    assert n == 1 and kept == [a, c, d], n
    many = [L("run the tests", command=f"npm test -- module{chr(97 + i)} --watch") for i in range(8)] + [c, d]
    got = pick(many, 3)
    assert c in got and d in got, got                                  # spread: the two unlike lessons survive 8 lookalikes
    sc = {lesson_id(e): 0.1 for e in many}
    sc[lesson_id(many[3])] = 5.0
    assert many[3] in pick(many, 1, sc)                                # surprise: the one the model gets wrong goes first
    out, rep = select([L("x")] + [a, b] + many, 4)
    assert rep["low_quality"] == 1 and rep["near_copies"] >= 1 and rep["kept"] == 4 and "picked" in describe(rep), rep
    assert needs_scores([a, c, d], 5) == [] and len(needs_scores([a, c, d], 2)) == 3
    print("select self-check ok")
