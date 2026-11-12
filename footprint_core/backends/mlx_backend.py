"""Apple Silicon backend: mlx-lm (train + OpenAI-compatible server)."""
import glob, json, os, re, shutil, signal, subprocess, sys, time

from .. import adapters, config


def _env():
    """Unbuffered (live progress) and offline when the model is cached: a network drop (laptop sleep)
    otherwise hangs mlx_lm's hub check forever — seen: 13h stuck at 0% CPU before iter 1. Cached = weights
    present (a tokenizer-only cache isn't enough)."""
    hub = os.path.join(os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub")
    cached = bool(glob.glob(os.path.join(hub, "models--" + config.MODEL.replace("/", "--"), "snapshots", "*", "*.safetensors")))
    return {**os.environ, "PYTHONUNBUFFERED": "1", **({"HF_HUB_OFFLINE": "1"} if cached else {})}


def _lengths():
    """Token count of every lesson (train/valid/test) with the model's own chat template."""
    os.environ.update({k: v for k, v in _env().items() if k == "HF_HUB_OFFLINE"})
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")  # no "PyTorch not found" noise: only the tokenizer is used
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(config.MODEL)
    out = []
    for name in ("train", "valid", "test"):
        p = os.path.join(config.DATA, f"{name}.jsonl")
        for line in open(p, encoding="utf-8") if os.path.exists(p) else ():
            e = json.loads(line)
            out.append(len(tok.apply_chat_template(e["messages"], tools=e.get("tools"), tokenize=True)))
    return out


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
    lengths = _lengths()
    seq = config.fit_seq(lengths)
    layers = config.lora_layers(config.model_config().get("num_hidden_layers"))
    iters = int(config.resolve_iters())
    every = max(25, iters // 10)
    sig = {"model": config.MODEL, "data": adapters.data_hash(), "rank": config.LORA_RANK, "layers": layers,
           "seq": seq, "iters": iters, "lr": config.LEARNING_RATE, "batch": config.BATCH}
    v, out, prog = adapters.start(sig)
    ckpt = force_ckpt or config.grad_ckpt(seq, layers)
    early = _count("valid") >= config.MIN_EVAL  # 1 validation lesson = noise: don't pick checkpoints by it
    offset = prog["done"] if prog else 0
    prog = prog or {"sig": sig, "iters": iters, "every": every, "done": 0, "val": {}, "best": None}
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
          f"max length {seq} tokens (longest lesson {max(lengths, default=0)}) · "
          f"grad checkpoint {'on' if ckpt else 'off'} · eval/save every {every}"
          + ("" if early else f"\n  note: only {_count('valid')} validation lessons (<{config.MIN_EVAL}) — early stop off, "
                               "keeping the final step. Collect more sessions for a real check."), flush=True)
    adapters.save_progress(out, prog)
    p = subprocess.Popen([sys.executable, "-m", "mlx_lm", "lora", "--model", config.MODEL, "--train",
                          "--data", config.DATA, "--adapter-path", out, "-c", cfg, "--mask-prompt",
                          "--num-layers", str(layers), "--learning-rate", config.LEARNING_RATE,
                          "--iters", str(iters - offset), "--steps-per-eval", str(every), "--save-every", str(every),
                          "--steps-per-report", "5", "--val-batches", "25", "--max-seq-length", str(seq),
                          "--batch-size", str(config.BATCH), *resume, *(["--grad-checkpoint"] if ckpt else [])],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_env())
    t0, tail = None, []
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
                    prog["best"] = [it, val]
                adapters.save_progress(out, prog)
                keep = {step_f(it), *([step_f(prog["best"][0])] if prog["best"] else [])}
                for f in glob.glob(os.path.join(out, "step*.safetensors")):
                    if f not in keep:
                        os.remove(f)  # 37-74 MB each: keep only the latest (resume) and the best (early stop)
            if "Starting training" in line:
                t0 = time.time()
            if t0 and (m := re.search(r"Iter (\d+): Train loss ([\d.]+)", line)):
                it = int(m.group(1))
                print(f"  step {offset + it}/{iters} · {100 * (offset + it) // iters}% · train loss {m.group(2)} · "
                      f"~{_eta(it, iters - offset, time.time() - t0)} left", flush=True)
            elif re.search(r"Val loss|Starting training|Trainable parameters|Error|Traceback", line):
                print(line, end="", flush=True)
    except KeyboardInterrupt:  # Ctrl-C, or SIGTERM (laptop job scheduler) via the handler below
        p.terminate()
        p.wait()
        sys.exit(f"\nstopped at step {prog['done']}/{iters}. Run `footprint train` again to resume from there.")
    finally:
        signal.signal(signal.SIGTERM, old_term)
    if p.wait():
        if OOM_RE.search("".join(tail)) and not ckpt:
            print("out of memory — retrying with grad checkpoint on (same result, less memory, slower)", flush=True)
            return train(force_ckpt=True)
        print("".join(tail[-15:]))
        sys.exit(f"training failed at step {prog['done']}/{iters}; run `footprint train` again to resume ({out})")
    final = os.path.join(out, "adapters.safetensors")  # = last step
    best = prog["best"][0] if early and prog["best"] else iters
    if best != iters and os.path.exists(step_f(best)):  # early stop: later steps overfit, keep the best one
        shutil.copy(step_f(best), final)
    for f in glob.glob(os.path.join(out, "step*.safetensors")) + glob.glob(os.path.join(out, "*_adapters.safetensors")) \
            + [os.path.join(out, "progress.json")]:
        if os.path.exists(f):
            os.remove(f)  # the pick is already adapters.safetensors (sync would upload them all)
    test = evaluate(out)
    adapters.finish(v, {"format": "native-v2", "iters": iters, "best_iter": best, "early_stop": early,
                        "val_loss": prog["val"].get(str(best)), "test_loss": test, "layers": layers, "seq": seq,
                        "grad_ckpt": ckpt, "rank": config.LORA_RANK, "lr": config.LEARNING_RATE})


OOM_RE = config.OOM


def evaluate(path=None):
    """Test loss of an adapter on the newest sessions (never trained or validated on). -> float"""
    path = path or config.ADAPTERS
    if not os.path.exists(os.path.join(path, "adapters.safetensors")):
        sys.exit("no trained adapter. run: footprint train")
    config.ensure_test()
    r = subprocess.run([sys.executable, "-m", "mlx_lm", "lora", "--model", config.MODEL,
                        "--data", config.DATA, "--adapter-path", path, "--mask-prompt",
                        "--test", "--max-seq-length", "4096", "--test-batches", str(config.TEST_BATCHES),
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
