"""Apple Silicon backend: mlx-lm (train + OpenAI-compatible server)."""
import os, subprocess, sys

from .. import config


def train():
    subprocess.run([sys.executable, "-m", "mlx_lm", "lora", "--model", config.MODEL, "--train",
                    "--data", config.DATA, "--adapter-path", config.ADAPTERS,
                    "--iters", config.ITERS, "--max-seq-length", "4096",
                    "--batch-size", "1", "--grad-checkpoint"], check=True)
    print(f"adapter saved -> {config.ADAPTERS}")


def serve():
    args = [sys.executable, "-m", "mlx_lm", "server", "--model", config.MODEL,
            "--host", "127.0.0.1", "--port", config.PORT]
    if os.path.exists(os.path.join(config.ADAPTERS, "adapters.safetensors")):
        args += ["--adapter-path", config.ADAPTERS]
    else:
        print("(no adapter yet — serving base model; run train first for footprint behavior)")
    print(f"OpenAI-compatible API: http://127.0.0.1:{config.PORT}/v1  (model name: footprint)")
    subprocess.run(args, check=True)
