"""Apple Silicon backend: mlx-lm (train + OpenAI-compatible server)."""
import glob, json, os, re, shutil, subprocess, sys

from .. import adapters, config


def _env():
    """Unbuffered (live progress) and offline when the model is cached: a network drop (laptop sleep)
    otherwise hangs mlx_lm's hub check forever — seen: 13h stuck at 0% CPU before iter 1. Cached = weights
    present (a tokenizer-only cache isn't enough)."""
    hub = os.path.join(os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub")
    cached = bool(glob.glob(os.path.join(hub, "models--" + config.MODEL.replace("/", "--"), "snapshots", "*", "*.safetensors")))
    return {**os.environ, "PYTHONUNBUFFERED": "1", **({"HF_HUB_OFFLINE": "1"} if cached else {})}


def train():
    """LoRA v2: native chat/tool format, loss on the answer only, rank 16 on every layer,
    best checkpoint by validation loss (early stop), new version gated on test loss."""
    iters = int(config.resolve_iters())
    every = max(25, iters // 10)
    v, out = adapters.new_version()
    cfg = os.path.join(out, "train_config.yaml")
    with open(cfg, "w") as f:  # JSON is valid YAML
        json.dump({"lora_parameters": {"rank": config.LORA_RANK, "scale": config.LORA_ALPHA / config.LORA_RANK,
                                       "dropout": 0.05}}, f)
    print(f"training {v}: {iters} iters, rank {config.LORA_RANK}, eval/save every {every} (batch {config.BATCH})")
    p = subprocess.Popen([sys.executable, "-m", "mlx_lm", "lora", "--model", config.MODEL, "--train",
                          "--data", config.DATA, "--adapter-path", out, "-c", cfg, "--mask-prompt",
                          "--num-layers", "-1", "--learning-rate", config.LEARNING_RATE,
                          "--iters", str(iters), "--steps-per-eval", str(every), "--save-every", str(every),
                          "--val-batches", "25", "--max-seq-length", "4096",
                          "--batch-size", str(config.BATCH), "--grad-checkpoint"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=_env())
    val = {}
    for line in p.stdout:
        print(line, end="", flush=True)
        if m := re.search(r"Iter (\d+): Val loss ([\d.]+)", line):
            val[int(m.group(1))] = float(m.group(2))
    if p.wait():
        sys.exit(f"training failed; partial output kept in {out}")
    saved = {it: l for it, l in val.items() if os.path.exists(os.path.join(out, f"{it:07d}_adapters.safetensors"))}
    best = min(saved, key=saved.get) if saved else None
    if best is not None and best != iters:  # early stop: later iters overfit, keep the best one
        shutil.copy(os.path.join(out, f"{best:07d}_adapters.safetensors"), os.path.join(out, "adapters.safetensors"))
    for f in glob.glob(os.path.join(out, "*_adapters.safetensors")):
        os.remove(f)  # 74 MB each; the best is already adapters.safetensors (sync would upload them all)
    test = evaluate(out)
    adapters.finish(v, {"format": "native-v2", "iters": iters, "best_iter": best or iters,
                        "val_loss": saved.get(best) if best else None, "test_loss": test,
                        "rank": config.LORA_RANK, "lr": config.LEARNING_RATE})


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
