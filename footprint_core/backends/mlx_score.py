"""Surprise scores: how wrong is the UNTRAINED base model on each lesson's answer?

  python -m footprint_core.backends.mlx_score <lessons.jsonl> <scores.json>

Score = mean cross-entropy on the answer tokens (same thing training minimises with --mask-prompt), no
adapter, no gradients. Low = the model already answers like this; high = something to learn. Dictionary
scores are computed for the answer positions only (hidden states -> output head on a slice), so a long
lesson costs about as much memory as a short one. Scores are cached per lesson; a stopped run continues.
"""
import json, os, sys, time

from .. import config, select


def _ids(r):
    if hasattr(r, "keys"):
        r = r["input_ids"]
    if len(r) and isinstance(r[0], (list, tuple)):
        r = r[0]
    return list(r)


def main(src, dst):
    import mlx.core as mx
    import mlx.nn as nn
    from mlx_lm import load
    try:
        cache = json.load(open(dst, encoding="utf-8"))
        if cache.get("model") != config.MODEL:
            raise ValueError
    except (OSError, ValueError):
        cache = {"model": config.MODEL, "scores": {}}
    rows = [json.loads(l) for l in open(src, encoding="utf-8")]
    todo = [e for e in rows if select.lesson_id(e) not in cache["scores"]]
    if not todo:
        return
    model, tok = load(config.MODEL)
    model.eval()
    inner = getattr(model, "model", None)
    head = (inner.embed_tokens.as_linear if inner is not None and getattr(model.args, "tie_word_embeddings", False)
            else getattr(model, "lm_head", None))

    def save():
        json.dump(cache, open(dst + ".tmp", "w", encoding="utf-8"))
        os.replace(dst + ".tmp", dst)

    t0 = time.time()
    for i, e in enumerate(todo, 1):
        ms, tools = e["messages"], e.get("tools")
        ids = _ids(tok.apply_chat_template(ms, tools=tools))
        off = len(_ids(tok.apply_chat_template(ms[:-1], tools=tools, add_generation_prompt=True)))
        off = max(1, min(off, len(ids) - 1))
        x, y = mx.array(ids[:-1])[None], mx.array(ids[off:])
        if inner is not None and head is not None:
            logits = head(inner(x)[:, off - 1:])       # answer positions only
        else:
            logits = model(x)[:, off - 1:]
        loss = nn.losses.cross_entropy(logits[0], y).mean().item()
        cache["scores"][select.lesson_id(e)] = round(loss, 4)
        mx.clear_cache()
        if i % 10 == 0 or i == len(todo):
            save()
            left = (time.time() - t0) / i * (len(todo) - i)
            print(f"  scored {i}/{len(todo)} lessons · ~{left / 60:.0f} min left" if left >= 90
                  else f"  scored {i}/{len(todo)} lessons · ~{left:.0f} s left", flush=True)
    save()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
