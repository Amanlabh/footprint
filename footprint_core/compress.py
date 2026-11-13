"""Opt-in context compression for TRAIN lessons (FOOTPRINT_COMPRESS=llmlingua).

LLMLingua-2 (Microsoft) is a small classifier that drops the words a reader needs least. Here it shortens
long tool outputs (file dumps, logs) inside a lesson's context — the bulkiest, least-studied part. The ask,
the assistant's own turns and the answer are never touched.

Why opt-in: the model then studies compressed context but gets full context from OpenCode at run time.
valid/test stay uncompressed on purpose, so the test loss shows what that mismatch costs. Keep it only if
the test loss holds.

  pip install llmlingua      (pulls torch; ~0.7 GB model on first use)
"""
import hashlib, json, os

from . import config

MODEL = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
MIN_CHARS = 600   # shorter tool outputs aren't worth compressing


def compress(rows, say=print):
    """rows: lessons. -> (rows with long tool outputs compressed, stats) — or (rows, None) if unavailable."""
    cache_f = os.path.join(config.DATA, "compress.json")
    try:
        cache = json.load(open(cache_f, encoding="utf-8"))
        if cache.get("rate") != config.COMPRESS_RATE:
            raise ValueError
    except (OSError, ValueError):
        cache = {"rate": config.COMPRESS_RATE, "out": {}}
    key = lambda t: hashlib.sha1(t.encode()).hexdigest()[:16]
    todo = {key(m["content"]): m["content"] for e in rows for m in e["messages"][1:-1]
            if m["role"] == "tool" and len(m.get("content") or "") >= MIN_CHARS and key(m["content"]) not in cache["out"]}
    if todo:
        try:
            from llmlingua import PromptCompressor
        except ImportError:
            say("  compression skipped: llmlingua is not installed. To use it: "
                f"{os.path.basename(config.VENV_PY)} -m pip install llmlingua")
            return rows, None
        say(f"  compressing {len(todo)} long tool outputs with LLMLingua-2 (first use downloads ~0.7 GB)…")
        pc = PromptCompressor(model_name=MODEL, use_llmlingua2=True, device_map="cpu")
        for i, (k, text) in enumerate(todo.items(), 1):
            cache["out"][k] = pc.compress_prompt(text, rate=config.COMPRESS_RATE,
                                                 force_tokens=["\n"])["compressed_prompt"]
            if i % 20 == 0:
                say(f"  compressed {i}/{len(todo)}")
        json.dump(cache, open(cache_f, "w", encoding="utf-8"))
    before = after = n = 0
    out = []
    for e in rows:
        ms = []
        for i, m in enumerate(e["messages"]):
            c = m.get("content") or ""
            if 0 < i < len(e["messages"]) - 1 and m["role"] == "tool" and key(c) in cache["out"]:
                new = cache["out"][key(c)]
                before, after, n = before + len(c), after + len(new), n + 1
                m = {**m, "content": new}
            ms.append(m)
        out.append({**e, "messages": ms})
    return out, {"outputs": n, "chars_before": before, "chars_after": after}
