"""Versioned LoRA adapters: adapters/<model>/vN/{adapters.safetensors, metrics.json} + `active`.

  footprint adapter               list versions (* = active) with their losses
  footprint adapter use v2        switch the live adapter (= rollback); restart `footprint serve`

A new version only goes live by itself when its test loss beats the active one; after that,
`footprint bench run footprint/<model>` is the gate before you keep it.
"""
import glob, hashlib, json, os, shutil, sys, time

from . import config


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


def finish(v, m):
    """Save metrics; go live only if no adapter is active or this one has a lower test loss."""
    m = {"version": v, "model": config.MODEL, "data": data_hash(), "created": time.strftime("%Y-%m-%d %H:%M"), **m}
    json.dump(m, open(os.path.join(config.MODEL_ADAPTERS, v, "metrics.json"), "w"), indent=1)
    cur = config.active_version()
    old = metrics(cur).get("test_loss") if cur else None
    if cur is None or (m.get("test_loss") is not None and (old is None or m["test_loss"] < old)):
        use(v, quiet=True)
        print(f"{v} is now active (test loss {m.get('test_loss')} vs {old if cur else 'none'}). "
              f"Gate it: footprint bench run <footprint model in opencode> --memory=both; rollback: footprint adapter use {cur}"
              if cur else f"{v} is now active.")
    else:
        print(f"{v} saved but NOT active: test loss {m.get('test_loss')} is not better than {cur}'s {old}. "
              f"Use anyway: footprint adapter use {v}")


def use(v, quiet=False):
    if v not in versions():
        sys.exit(f"no {v}. have: {', '.join(versions()) or 'none'}")
    open(os.path.join(config.MODEL_ADAPTERS, "active"), "w", encoding="utf-8").write(v)
    if not quiet:
        print(f"active adapter: {v} — restart the server to load it (footprint serve, or re-run footprint install)")


def main(argv=()):
    migrate()
    if argv[:1] == ["use"] and len(argv) > 1:
        return use(argv[1])
    cur = config.active_version()
    print(f"adapters for {config.MODEL}:")
    for v in versions():
        m = metrics(v)
        print(f"  {'*' if v == cur else ' '} {v}  {m.get('format', ''):<22} test loss {m.get('test_loss', '?')}  "
              f"val {m.get('val_loss', '?')}  best iter {m.get('best_iter', '?')}  data {m.get('data', '?')}  {m.get('created', '')}")
    if not versions():
        print("  none yet. run: footprint collect && footprint train")


if __name__ == "__main__":  # self-check: versions, gate, migrate, rollback in a temp root
    import tempfile
    d = tempfile.mkdtemp()
    config.ADAPTER_ROOT, config.DATA = d, d
    config.MODEL_ADAPTERS = os.path.join(d, "m")
    open(os.path.join(d, "adapters.safetensors"), "w").write("old")
    v, p = new_version()  # migrates legacy to v1 (active), returns v2
    assert v == "v2" and versions() == ["v1", "v2"] and config.active_version() == "v1", (v, versions())
    finish("v2", {"test_loss": 2.0, "format": "native-v2"})
    assert config.active_version() == "v2"  # legacy had no test loss: v2 wins
    v3, _ = new_version()
    finish(v3, {"test_loss": 2.5})
    assert config.active_version() == "v2"  # worse: saved, not live
    use("v3", quiet=True)
    assert config.active_version() == "v3"
    use("v2", quiet=True)  # rollback
    assert config.active_version() == "v2" and metrics("v3")["test_loss"] == 2.5
    # resume: unfinished v4 with matching sig resumes; changed sig wipes + reuses v4; finished -> v5
    v4, p4 = new_version()
    save_progress(p4, {"sig": {"a": 1}, "iters": 100, "done": 50})
    assert start({"a": 1})[0::2] == ("v4", {"sig": {"a": 1}, "iters": 100, "done": 50})
    v, p, prog = start({"a": 2})
    assert (v, prog) == ("v4", None) and os.listdir(p) == []
    json.dump({}, open(os.path.join(p, "metrics.json"), "w"))
    assert start({"a": 2})[0] == "v5"
    print("adapters self-check ok")
