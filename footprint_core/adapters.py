"""Versioned LoRA adapters: adapters/<model>/vN/{adapters.safetensors, metrics.json} + `active`.

  footprint adapter               list versions (* = active) with their losses
  footprint adapter use v2        switch the live adapter (= rollback); Ollama model is rebuilt

A new version only goes live by itself when its test loss beats both the base model and the active
version, all scored on the SAME test set (collect makes a new one each time); after that,
`footprint bench run footprint/<model>` is the gate before you keep it.
"""
import glob, hashlib, json, os, shutil, sys, tempfile, time

from . import config, ollama


def versions():
    return sorted((os.path.basename(d) for d in glob.glob(os.path.join(config.MODEL_ADAPTERS, "v*"))
                   if os.path.basename(d)[1:].isdigit()), key=lambda v: int(v[1:]))


def metrics(v):
    try:
        return json.load(open(os.path.join(config.MODEL_ADAPTERS, v, "metrics.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def migrate():
    """v1 format (adapters/ root, custom <tool> format) -> adapters/<model>/v1, kept for rollback."""
    old = os.path.join(config.ADAPTER_ROOT, "adapters.safetensors")
    if not os.path.exists(old):
        return
    dst = os.path.join(config.MODEL_ADAPTERS, "v1")
    os.makedirs(dst, exist_ok=True)
    for f in glob.glob(os.path.join(config.ADAPTER_ROOT, "*.safetensors")) + \
            glob.glob(os.path.join(config.ADAPTER_ROOT, "adapter_config.json")):
        shutil.move(f, os.path.join(dst, os.path.basename(f)))
    json.dump({"version": "v1", "format": "legacy <tool> text", "note": "trained before v2; 100 iters"},
              open(os.path.join(dst, "metrics.json"), "w"), indent=1)
    if not config.active_version():
        use("v1", quiet=True)


def new_version():
    migrate()
    vs = versions()
    v = f"v{int(vs[-1][1:]) + 1 if vs else 1}"
    path = os.path.join(config.MODEL_ADAPTERS, v)
    os.makedirs(path)
    return v, path


def start(sig):
    """Where a training run goes. An unfinished newest version (no metrics.json) with the same data + LoRA
    settings is resumed -> (v, path, progress). Unfinished with other settings is wiped and reused (its
    checkpoints can't load under a different LoRA shape). Otherwise a fresh version -> (v, path, None)."""
    migrate()
    vs = versions()
    last = vs[-1] if vs else None
    if last and not os.path.exists(os.path.join(config.MODEL_ADAPTERS, last, "metrics.json")) \
            and last != config.active_version():
        path = os.path.join(config.MODEL_ADAPTERS, last)
        try:
            prog = json.load(open(os.path.join(path, "progress.json"), encoding="utf-8"))
        except (OSError, ValueError):
            prog = {}
        if prog.get("sig") == sig and 0 < prog.get("done", 0) < prog.get("iters", 0):
            return last, path, prog
        print(f"discarding unfinished {last} (stopped before any checkpoint, or data/settings changed since)")
        shutil.rmtree(path)
        os.makedirs(path)
        return last, path, None
    v, path = new_version()
    return v, path, None


def save_progress(path, prog):
    tmp = os.path.join(path, "progress.json.tmp")
    json.dump(prog, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, os.path.join(path, "progress.json"))


def data_hash():
    h = hashlib.sha256()
    for name in ("train", "valid", "test"):
        p = os.path.join(config.DATA, f"{name}.jsonl")
        if os.path.exists(p):
            h.update(open(p, "rb").read())
    return h.hexdigest()[:12]


def test_hash():
    p = os.path.join(config.DATA, "test.jsonl")
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:12] if os.path.exists(p) else None


def _zeroed(path):
    """Copy of an adapter with every lora_b/lora_B = 0: scores exactly as the base model, through the same
    evaluate(). -> temp dir"""
    import numpy as np
    from safetensors.numpy import load_file, save_file
    d = tempfile.mkdtemp()
    for f in os.listdir(path):
        src = os.path.join(path, f)
        if f in ("adapters.safetensors", "adapter_model.safetensors"):
            save_file({k: np.zeros_like(t) if "lora_b" in k.lower() else t for k, t in load_file(src).items()},
                      os.path.join(d, f))
        elif f.endswith(".json"):
            shutil.copy(src, d)
    return d


def _on_this_test(v, t, score):
    """Test loss of version v on test set t: its stored one if scored on t, else score it now (and store)."""
    m = metrics(v)
    if m.get("test_set") == t and m.get("test_loss") is not None:
        return m["test_loss"]
    print(f"re-scoring {v} on the current test set (its {m.get('test_loss')} was on another one)…", flush=True)
    loss = score(os.path.join(config.MODEL_ADAPTERS, v))
    if loss is not None:
        json.dump({**m, "test_loss": loss, "test_set": t}, open(os.path.join(config.MODEL_ADAPTERS, v, "metrics.json"), "w"),
                  indent=1)
    return loss


def finish(v, m, score=None):
    """Save metrics; go live only if the test loss beats the base model and the active version on the same
    test set. score(adapter_dir) -> test loss: re-scores what was measured on an older test set."""
    t = test_hash()
    m = {"version": v, "model": config.MODEL, "data": data_hash(), "test_set": t,
         "created": time.strftime("%Y-%m-%d %H:%M"), **m}
    path = os.path.join(config.MODEL_ADAPTERS, v)
    base = next((metrics(x)["base_loss"] for x in versions() if x != v and metrics(x).get("test_set") == t
                 and metrics(x).get("base_loss") is not None), None)
    if base is None and score and m.get("test_loss") is not None:
        print("scoring the base model (no adapter) on the same test set…", flush=True)
        z = _zeroed(path)
        base = score(z)
        shutil.rmtree(z, ignore_errors=True)
    m["base_loss"] = base
    json.dump(m, open(os.path.join(path, "metrics.json"), "w"), indent=1)
    new, cur = m.get("test_loss"), config.active_version()
    old = _on_this_test(cur, t, score) if cur and score else (metrics(cur).get("test_loss") if cur else None)
    rivals = [(n, x) for n, x in (("base model", base), (cur, old)) if x is not None]
    lost = next(((n, x) for n, x in rivals if new is None or new >= x), None)
    vs = ", ".join(f"{n} {x}" for n, x in rivals) or "nothing to compare"
    if lost:
        print(f"{v} saved but NOT active: test loss {new} is not better than {lost[0]}'s {lost[1]} (same test set; {vs}). "
              f"Use anyway: footprint adapter use {v}")
        return
    use(v, quiet=True)
    ollama.refresh()
    print(f"{v} is now active (test loss {new} vs {vs}). "
          f"Gate it: footprint bench run <footprint model in opencode> --memory=both"
          + (f"; rollback: footprint adapter use {cur}" if cur else ""))


def use(v, quiet=False):
    if v not in versions():
        sys.exit(f"no {v}. have: {', '.join(versions()) or 'none'}")
    open(os.path.join(config.MODEL_ADAPTERS, "active"), "w", encoding="utf-8").write(v)
    if not quiet:
        print(f"active adapter: {v}")
        ollama.refresh()


def main(argv=()):
    migrate()
    if argv[:1] == ["use"] and len(argv) > 1:
        return use(argv[1])
    cur = config.active_version()
    print(f"adapters for {config.MODEL}:  (compare test losses only within the same test set)")
    for v in versions():
        m = metrics(v)
        print(f"  {'*' if v == cur else ' '} {v}  {m.get('format', ''):<22} test loss {m.get('test_loss', '?')}  "
              f"base {m.get('base_loss', '?')}  test set {m.get('test_set', '?')}  val {m.get('val_loss', '?')}  best iter {m.get('best_iter', '?')}  data {m.get('data', '?')}  {m.get('created', '')}")
    if not versions():
        print("  none yet. run: footprint collect && footprint train")


if __name__ == "__main__":  # self-check: versions, gate, migrate, rollback in a temp root
    ollama.refresh = lambda: None  # no real Ollama rebuild from a temp root
    d = tempfile.mkdtemp()
    config.ADAPTER_ROOT, config.DATA = d, d
    config.MODEL_ADAPTERS = os.path.join(d, "m")
    open(os.path.join(d, "adapters.safetensors"), "w").write("old")
    open(os.path.join(d, "test.jsonl"), "w").write("A")
    v, p = new_version()  # migrates legacy to v1 (active), returns v2
    assert v == "v2" and versions() == ["v1", "v2"] and config.active_version() == "v1", (v, versions())
    finish("v2", {"test_loss": 2.0, "format": "native-v2"})
    assert config.active_version() == "v2"  # legacy had no test loss: v2 wins
    v3, _ = new_version()
    finish(v3, {"test_loss": 2.5})
    assert config.active_version() == "v2"  # worse: saved, not live
    # new test set: v2's 2.0 is not comparable -> re-scored (3.0 here), so 2.7 wins; base scored once (2.9)
    import numpy as np
    from safetensors.numpy import load_file, save_file
    open(os.path.join(d, "test.jsonl"), "w").write("B")
    def score(p):  # zeroed copy (= base) 2.9, old v2 3.0
        w = os.path.join(p, "adapters.safetensors")
        return 2.9 if os.path.exists(w) and not load_file(w)["l.lora_b"].any() else {"v2": 3.0}[os.path.basename(p)]
    vb, pb = new_version()
    save_file({"l.lora_a": np.ones((2, 2), np.float32), "l.lora_b": np.ones((2, 2), np.float32)}, os.path.join(pb, "adapters.safetensors"))
    finish(vb, {"test_loss": 2.7}, score)
    assert config.active_version() == vb and metrics("v2")["test_loss"] == 3.0 and metrics(vb)["base_loss"] == 2.9
    vc, _ = new_version()
    finish(vc, {"test_loss": 2.95}, score)  # base reused from vb (same test set), 2.95 >= 2.9: not live
    assert config.active_version() == vb and metrics(vc)["base_loss"] == 2.9
    use("v2", quiet=True)
    use("v3", quiet=True)
    assert config.active_version() == "v3"
    use("v2", quiet=True)  # rollback
    assert config.active_version() == "v2" and metrics("v3")["test_loss"] == 2.5
    # resume: unfinished newest with matching sig resumes; changed sig wipes + reuses it; finished -> next
    vr, pr = new_version()
    save_progress(pr, {"sig": {"a": 1}, "iters": 100, "done": 50})
    assert start({"a": 1})[0::2] == (vr, {"sig": {"a": 1}, "iters": 100, "done": 50})
    v, p, prog = start({"a": 2})
    assert (v, prog) == (vr, None) and os.listdir(p) == []
    json.dump({}, open(os.path.join(p, "metrics.json"), "w"))
    assert start({"a": 2})[0] == f"v{int(vr[1:]) + 1}"
    print("adapters self-check ok")
