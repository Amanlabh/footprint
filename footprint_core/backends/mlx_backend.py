"""Apple Silicon backend: mlx-lm (train + OpenAI-compatible server)."""
import glob, json, os, re, shutil, signal, subprocess, sys, time

from .. import adapters, compress, config, select


def _env():
    """Unbuffered (live progress) and offline when the model is cached: a network drop (laptop sleep)
    otherwise hangs mlx_lm's hub check forever — seen: 13h stuck at 0% CPU before iter 1. Cached = weights
    present (a tokenizer-only cache isn't enough)."""
    hub = os.path.join(os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub")
    cached = bool(glob.glob(os.path.join(hub, "models--" + config.MODEL.replace("/", "--"), "snapshots", "*", "*.safetensors")))
    return {**os.environ, "PYTHONUNBUFFERED": "1", **({"HF_HUB_OFFLINE": "1"} if cached else {})}


def _plan(quick=False):
    """Fit the lessons to this machine. Measures every lesson (train/valid/test) with the model's own chat
    template; lessons longer than what the RAM can train on (config.seq_cap) lose their oldest context —
    mlx_lm itself would cut the END of a long lesson, i.e. the answer we train on.
    Then (select.py) the train split is cut to the STEP_BUDGET lessons that teach the most.
    quick: skip selection (standalone `eval` only needs the fitted test split).
    -> {seq, data (dir to train from), longest, cap, trimmed, dropped, picked, squeezed, train_n, valid_n}"""
    os.environ.update({k: v for k, v in _env().items() if k == "HF_HUB_OFFLINE"})
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")  # no "PyTorch not found" noise: only the tokenizer is used
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(config.MODEL)
    cap, sets, lengths, trimmed, dropped = config.seq_cap(), {}, [], 0, 0
    for name in ("train", "valid", "test"):
        p = os.path.join(config.DATA, f"{name}.jsonl")
        rows = []
        for line in open(p, encoding="utf-8") if os.path.exists(p) else ():
            e = json.loads(line)
            count = lambda ms: config.ntok(tok.apply_chat_template(ms, tools=e.get("tools"), tokenize=True))
            n = count(e["messages"])
            lengths.append(n)
            if n > cap:
                ms = config.trim(e["messages"], count, cap)
                if ms is None:
                    dropped += 1
                    continue
                trimmed += 1
                e, n = {**e, "messages": ms}, count(ms)
            rows.append((n, e))
        sets[name] = rows
    picked = squeezed = None
    if config.SELECT and not quick:  # train split only: valid/test stay as collected, so losses stay comparable
        rows = [e for _, e in sets["train"]]
        scores, need = None, select.needs_scores(rows, config.STEP_BUDGET)
        if need:
            scores = _scores(need)
        rows, picked = select.select(rows, config.STEP_BUDGET, scores)
        if config.COMPRESS == "llmlingua":
            rows, squeezed = compress.compress(rows)
        n_of = lambda e: config.ntok(tok.apply_chat_template(e["messages"], tools=e.get("tools"), tokenize=True))
        sets["train"] = [(n_of(e), e) for e in rows]
    data = config.DATA
    changed = trimmed or dropped or squeezed or (picked and picked["kept"] < picked["start"])
    if changed:  # a ready-to-train copy; the collected data stays as it is
        data = os.path.join(config.DATA, "ready")
        os.makedirs(data, exist_ok=True)
        for name, rows in sets.items():
            with open(os.path.join(data, f"{name}.jsonl"), "w", encoding="utf-8") as fh:
                fh.writelines(json.dumps(e) + "\n" for _, e in rows)
    kept = [n for rows in sets.values() for n, _ in rows]
    return {"seq": config.fit_seq(kept), "data": data, "longest": max(lengths, default=0), "cap": cap,
            "trimmed": trimmed, "dropped": dropped, "total": len(lengths), "picked": picked, "squeezed": squeezed,
            "train_n": len(sets["train"]), "valid_n": len(sets["valid"])}


def _scores(rows):
    """Base-model loss per lesson (backends/mlx_score.py), in its own process so its memory is freed before
    training. Cached in data/scores.json. -> {lesson_id: loss}, or None if scoring failed (pick by spread only)."""
    src, dst = os.path.join(config.DATA, "score_in.jsonl"), os.path.join(config.DATA, "scores.json")
    with open(src, "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(e) + "\n" for e in rows)
    print(f"finding the lessons that teach the most ({len(rows)} candidates, budget {config.STEP_BUDGET}): "
          "the untrained model tries each one…", flush=True)
    r = subprocess.run([sys.executable, "-m", "footprint_core.backends.mlx_score", src, dst], cwd=config.ROOT, env=_env())
    os.remove(src)
    try:
        return json.load(open(dst, encoding="utf-8"))["scores"]
    except (OSError, ValueError, KeyError):
        print(f"  scoring failed (exit {r.returncode}) — picking by variety only")
        return None


def _count(name):
    p = os.path.join(config.DATA, f"{name}.jsonl")
    return sum(1 for _ in open(p, encoding="utf-8")) if os.path.exists(p) else 0


def _eta(done, total, secs):
    left = secs / max(done, 1) * (total - done)
    return f"{left / 60:.0f} min" if left >= 90 else f"{left:.0f} s"


def train(force_ckpt=False):
    """LoRA v2: native chat/tool format, loss on the answer only, rank 16 on the last half of the layers,
    max length fitted to the data, best checkpoint by validation loss (early stop), new version gated on
    test loss. Prints % + time left; a stopped run resumes from its last checkpoint on the next `train`."""
    print("measuring your lessons (tokens)…", flush=True)
    plan = _plan()
    seq = plan["seq"]
    layers = config.lora_layers(config.model_config().get("num_hidden_layers"))
    iters = int(config.resolve_iters(plan["train_n"], config.STEP_BUDGET if config.SELECT else None))
    every = max(25, iters // 10)
    sig = {"model": config.MODEL, "data": adapters.data_hash(), "rank": config.LORA_RANK, "layers": layers,
           "seq": seq, "iters": iters, "lr": config.LEARNING_RATE, "batch": config.BATCH,
           "train_n": plan["train_n"], "compress": config.COMPRESS}
    v, out, prog = adapters.start(sig)
    ckpt = force_ckpt or config.grad_ckpt(seq, layers)
    early = plan["valid_n"] >= config.MIN_EVAL  # 1 validation lesson = noise: don't pick checkpoints by it
    offset = prog["done"] if prog else 0
    prog = prog or {"sig": sig, "iters": iters, "every": every, "done": 0, "val": {}, "best": None, "stale": 0}
    cfg = os.path.join(out, "train_config.yaml")
    with open(cfg, "w") as f:  # JSON is valid YAML
        json.dump({"lora_parameters": {"rank": config.LORA_RANK, "scale": config.LORA_ALPHA / config.LORA_RANK,
                                       "dropout": 0.05}}, f)
    # checkpoints are kept as step<GLOBAL>.safetensors: mlx restarts its counter at 1 on resume and names
    # files by its own step, so each save is renamed at once (global = offset + mlx step)
    step_f = lambda it: os.path.join(out, f"step{it:07d}.safetensors")
    resume = []
    if offset:
        if not os.path.exists(step_f(offset)):
            print(f"checkpoint for step {offset} missing — starting {v} over")
            shutil.rmtree(out)
            os.makedirs(out)
            return train(force_ckpt)
        for f in glob.glob(os.path.join(out, "*_adapters.safetensors")):
            os.remove(f)  # strays from a crash between save and rename
        resume = ["--resume-adapter-file", step_f(offset)]
        print(f"resuming {v} from step {offset}/{iters}")
    print(f"training {v}: {iters} steps · LoRA rank {config.LORA_RANK} on last {layers} layers · "
          f"max length {seq} tokens (longest lesson {plan['longest']}) · "
          f"grad checkpoint {'on' if ckpt else 'off'} · eval/save every {every}"
          + (f"\n  lessons: {select.describe(plan['picked'])}. Train on everything: FOOTPRINT_SELECT=off"
             if plan["picked"] and plan["picked"]["kept"] < plan["picked"]["start"] else "")
          + (f"\n  compressed {plan['squeezed']['outputs']} long tool outputs: {plan['squeezed']['chars_before']} -> "
             f"{plan['squeezed']['chars_after']} chars (train only; test stays uncompressed)" if plan["squeezed"] else "")
          + (f"\n  fitted to this machine ({config.ram_gb() or 0:.0f} GB RAM -> up to {plan['cap']} tokens per lesson): "
             f"{plan['trimmed']} of {plan['total']} lessons lost their oldest context (answer kept whole)"
             + (f", {plan['dropped']} too long even then and skipped" if plan["dropped"] else "")
             + ". Override: FOOTPRINT_MAX_SEQ" if plan["trimmed"] or plan["dropped"] else "")
          + ("" if early else f"\n  note: only {_count('valid')} validation lessons (<{config.MIN_EVAL}) — early stop off, "
                               "keeping the final step. Collect more sessions for a real check."), flush=True)
    adapters.save_progress(out, prog)
    p = subprocess.Popen([sys.executable, "-m", "mlx_lm", "lora", "--model", config.MODEL, "--train",
                          "--data", plan["data"], "--adapter-path", out, "-c", cfg, "--mask-prompt",
                          "--num-layers", str(layers), "--learning-rate", config.LEARNING_RATE,
                          "--iters", str(iters - offset), "--steps-per-eval", str(every), "--save-every", str(every),
                          "--steps-per-report", "5", "--val-batches", str(config.VAL_BATCHES), "--max-seq-length", str(seq),
                          "--batch-size", str(config.BATCH), *resume, *(["--grad-checkpoint"] if ckpt else [])],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_env())
    t0, tail, plateau = None, [], False
    g = lambda it: offset + it if it > 1 or not offset else offset  # resumed iter 1 val = state at `offset`

    def _term(*_):
        raise KeyboardInterrupt
    old_term = signal.signal(signal.SIGTERM, _term)
    try:
        for line in p.stdout:
            tail = (tail + [line])[-30:]
            if m := re.search(r"Iter (\d+): Val loss ([\d.]+)", line):
                prog["val"][str(g(int(m.group(1))))] = float(m.group(2))
            if m := re.search(r"Iter (\d+): Saved adapter weights", line):
                local = int(m.group(1))
                it = g(local)
                os.replace(os.path.join(out, f"{local:07d}_adapters.safetensors"), step_f(it))
                prog["done"] = it
                val = prog["val"].get(str(it))
                if val is not None and (not prog["best"] or val < prog["best"][1]):
                    prog["best"], prog["stale"] = [it, val], 0
                elif val is not None:
                    prog["stale"] = prog.get("stale", 0) + 1
                adapters.save_progress(out, prog)
                keep = {step_f(it), *([step_f(prog["best"][0])] if prog["best"] else [])}
                for f in glob.glob(os.path.join(out, "step*.safetensors")):
                    if f not in keep:
                        os.remove(f)  # 37-74 MB each: keep only the latest (resume) and the best (early stop)
                if early and prog.get("stale", 0) >= config.PATIENCE and it < iters:
                    print(f"  validation loss has not improved for {prog['stale']} checks (best {prog['best'][1]} at step "
                          f"{prog['best'][0]}) — stopping here, {iters - it} steps saved", flush=True)
                    plateau = True
                    p.terminate()
                    break
            if "Starting training" in line:
                t0 = time.time()
            if t0 and (m := re.search(r"Iter (\d+): Train loss ([\d.]+)", line)):
                it = int(m.group(1))
                mem = re.search(r"Peak mem ([\d.]+) GB", line)
                print(f"  step {offset + it}/{iters} · {100 * (offset + it) // iters}% · train loss {m.group(2)} · "
                      f"~{_eta(it, iters - offset, time.time() - t0)} left" + (f" · mem {mem.group(1)} GB" if mem else ""), flush=True)
            elif re.search(r"Val loss|Starting training|Trainable parameters|Error|Traceback", line):
                print(line, end="", flush=True)
    except KeyboardInterrupt:  # Ctrl-C, or SIGTERM (laptop job scheduler) via the handler below
        p.terminate()
        p.wait()
        sys.exit(f"\nstopped at step {prog['done']}/{iters}. Run `footprint train` again to resume from there.")
    finally:
        signal.signal(signal.SIGTERM, old_term)
    if p.wait() and not plateau:
        if OOM_RE.search("".join(tail)) and not ckpt:
            print("out of memory — retrying with grad checkpoint on (same result, less memory, slower)", flush=True)
            return train(force_ckpt=True)
        print("".join(tail[-15:]))
        sys.exit(f"training failed at step {prog['done']}/{iters}; run `footprint train` again to resume ({out})")
    final = os.path.join(out, "adapters.safetensors")  # = last step
    best = prog["best"][0] if early and prog["best"] else iters
    last = prog["val"].get(str(iters))  # the final step is scored but not a numbered save: let it win too
    if early and not plateau and prog["best"] and last is not None and last <= prog["best"][1]:
        best = iters
    if best != iters and os.path.exists(step_f(best)):  # early stop: later steps overfit, keep the best one
        shutil.copy(step_f(best), final)
    if plateau and not os.path.exists(final):
        shutil.copy(step_f(best), final)
    for f in glob.glob(os.path.join(out, "step*.safetensors")) + glob.glob(os.path.join(out, "*_adapters.safetensors")) \
            + [os.path.join(out, "progress.json")]:
        if os.path.exists(f):
            os.remove(f)  # the pick is already adapters.safetensors (sync would upload them all)
    test = evaluate(out, plan)
    adapters.finish(v, {"format": "native-v2", "iters": iters, "best_iter": best, "early_stop": early,
                        "stopped_at": prog["done"] if plateau else iters, "lessons": plan["train_n"],
                        "picked_from": plan["picked"]["start"] if plan["picked"] else plan["train_n"],
                        "val_loss": prog["val"].get(str(best)), "test_loss": test, "layers": layers, "seq": seq,
                        "grad_ckpt": ckpt, "rank": config.LORA_RANK, "lr": config.LEARNING_RATE})


OOM_RE = config.OOM


def evaluate(path=None, plan=None):
    """Test loss of an adapter on the newest sessions (never trained or validated on). -> float
    Scored on the same fitted lessons and max length the machine trains with."""
    path = path or config.ADAPTERS
    if not os.path.exists(os.path.join(path, "adapters.safetensors")):
        sys.exit("no trained adapter. run: footprint train")
    config.ensure_test()
    plan = plan or _plan(quick=True)
    print("scoring on the held-out test lessons…", flush=True)
    r = subprocess.run([sys.executable, "-m", "mlx_lm", "lora", "--model", config.MODEL,
                        "--data", plan["data"], "--adapter-path", path, "--mask-prompt",
                        "--test", "--max-seq-length", str(plan["seq"]), "--test-batches", str(config.TEST_BATCHES),
                        "--batch-size", str(config.BATCH)], capture_output=True, text=True, env=_env())
    print(r.stdout[-400:] + r.stderr[-400:] if r.returncode else r.stdout.strip().splitlines()[-1])
    m = re.search(r"Test loss ([\d.]+)", r.stdout)
    return float(m.group(1)) if m else None


def serve():
    args = [sys.executable, "-m", "mlx_lm", "server", "--model", config.MODEL,
            "--host", "127.0.0.1", "--port", config.PORT]
    if config.has_adapter():
        args += ["--adapter-path", config.ADAPTERS]
        print(f"adapter: {config.active_version()}")
    else:
        print("(no adapter yet — serving base model; run train first for footprint behavior)")
    print(f"OpenAI-compatible API: http://127.0.0.1:{config.PORT}/v1  (model name: footprint)")
    subprocess.run(args, check=True)
