"""Opt-in context compression for TRAIN lessons (FOOTPRINT_COMPRESS=llmlingua or ctxprune).

LLMLingua-2 (Microsoft) is a small classifier that drops the words a reader needs least. Here it shortens
long tool outputs (file dumps, logs) inside a lesson's context — the bulkiest, least-studied part. The ask,
the assistant's own turns and the answer are never touched.

ctxprune is a drop-in for the same call (ctxprune.compat.PromptCompressor): a 140M int8 ONNX model on CPU,
~143 MB on first use and no torch, and with protect=True (set here) it never drops an identifier, path or number.

Why opt-in: the model then studies compressed context but gets full context from OpenCode at run time.
valid/test stay uncompressed on purpose, so the test loss shows what that mismatch costs. Keep it only if
the test loss holds.

  pip install llmlingua      (pulls torch; ~0.7 GB model on first use)
  pip install ctxprune       (CPU only, ~143 MB model on first use)
"""
import hashlib, json, os

from . import config

MODEL = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
MIN_CHARS = 600   # shorter tool outputs aren't worth compressing


def compress(rows, say=print, backend="llmlingua"):
    """rows: lessons. -> (rows with long tool outputs compressed, stats) — or (rows, None) if unavailable."""
    cache_f = os.path.join(config.DATA, "compress.json")
    try:
        cache = json.load(open(cache_f, encoding="utf-8"))
        if cache.get("rate") != config.COMPRESS_RATE or cache.get("backend", "llmlingua") != backend:
            raise ValueError
    except (OSError, ValueError):
        cache = {"rate": config.COMPRESS_RATE, "backend": backend, "out": {}}
    key = lambda t: hashlib.sha1(t.encode()).hexdigest()[:16]
    todo = {key(m["content"]): m["content"] for e in rows for m in e["messages"][1:-1]
            if m["role"] == "tool" and len(m.get("content") or "") >= MIN_CHARS and key(m["content"]) not in cache["out"]}
    if todo:
        try:
            if backend == "ctxprune":
                from ctxprune.compat import PromptCompressor
            else:
                from llmlingua import PromptCompressor
        except ImportError:
            say(f"  compression skipped: {backend} is not installed. To use it: "
                f"{os.path.basename(config.VENV_PY)} -m pip install {backend}")
            return rows, None
        size = "~143 MB" if backend == "ctxprune" else "~0.7 GB"
        say(f"  compressing {len(todo)} long tool outputs with {backend} (first use downloads {size})…")
        extra = {"protect": True} if backend == "ctxprune" else {}  # ctxprune: never drop an ID, number or path
        pc = PromptCompressor(model_name=MODEL, use_llmlingua2=True, device_map="cpu")
        for i, (k, text) in enumerate(todo.items(), 1):
            cache["out"][k] = pc.compress_prompt(text, rate=config.COMPRESS_RATE, force_tokens=["\n"],
                                                 **extra)["compressed_prompt"]
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
