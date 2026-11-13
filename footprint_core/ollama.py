"""Serve through Ollama: LoRA adapter -> GGUF adapter -> `ollama create footprint` on Ollama's own base.

  adapters/<model>/vN/adapters.safetensors (MLX)  or  adapter_model.safetensors (PEFT, torch backend)
    -> vN/adapter.gguf  (a few MB; llama.cpp LoRA format)
    -> Modelfile: FROM <ollama base>  ADAPTER vN/adapter.gguf
    -> model "footprint" at http://127.0.0.1:11434/v1  (Ollama runs itself: app / brew service / systemd)
"""
import json, os, re, shutil, subprocess, sys, urllib.request

from . import config

URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if "://" not in URL:
    URL = "http://" + URL
NAME = "footprint"
# HF layer names -> llama.cpp/GGUF names (Qwen2 / Llama-style blocks)
PROJ = {"self_attn.q_proj": "attn_q", "self_attn.k_proj": "attn_k", "self_attn.v_proj": "attn_v",
        "self_attn.o_proj": "attn_output", "mlp.gate_proj": "ffn_gate", "mlp.up_proj": "ffn_up",
        "mlp.down_proj": "ffn_down"}


def base():
    """Ollama tag of the same base model footprint trained on."""
    if os.environ.get("FOOTPRINT_OLLAMA_BASE"):
        return os.environ["FOOTPRINT_OLLAMA_BASE"]
    m = re.search(r"Qwen2\.5-Coder-([\d.]+)B", config.MODEL, re.I)
    if not m:
        sys.exit(f"no Ollama base known for {config.MODEL}. set FOOTPRINT_OLLAMA_BASE (e.g. qwen2.5-coder:7b)")
    return f"qwen2.5-coder:{m.group(1)}b"


def _lora(path):
    """-> ({(layer, proj): (A[r,in], B[out,r])}, alpha) from an MLX or PEFT adapter dir."""
    from safetensors.numpy import load_file
    cfg = json.load(open(os.path.join(path, "adapter_config.json"), encoding="utf-8"))
    pairs = {}
    if os.path.exists(os.path.join(path, "adapter_model.safetensors")):  # PEFT: lora_A.weight [r,in], lora_B.weight [out,r]
        for k, t in load_file(os.path.join(path, "adapter_model.safetensors")).items():
            m = re.search(r"layers\.(\d+)\.(\w+\.\w+)\.lora_([AB])", k)
            if m:
                pairs.setdefault((int(m[1]), m[2]), {})[m[3]] = t
        alpha = float(cfg["lora_alpha"])
    else:  # MLX: lora_a [in,r], lora_b [r,out]; y += scale * x@a@b
        for k, t in load_file(os.path.join(path, "adapters.safetensors")).items():
            m = re.search(r"layers\.(\d+)\.(\w+\.\w+)\.lora_([ab])", k)
            if m:
                pairs.setdefault((int(m[1]), m[2]), {})[m[3].upper()] = t.T
        p = cfg["lora_parameters"]
        alpha = float(p["scale"]) * p["rank"]  # llama.cpp applies alpha/rank
    return {k: (v["A"], v["B"]) for k, v in pairs.items()}, alpha


def export(path):
    """Write <path>/adapter.gguf. -> its path."""
    try:
        import gguf, numpy as np
    except ImportError:
        sys.exit("missing the gguf package (needed to hand the adapter to Ollama). run: footprint setup")
    pairs, alpha = _lora(path)
    if not pairs:
        sys.exit(f"no LoRA tensors in {path}")
    out = os.path.join(path, "adapter.gguf")
    w = gguf.GGUFWriter(out, "qwen2")
    w.add_type(gguf.GGUFType.ADAPTER)
    w.add_string(gguf.Keys.Adapter.TYPE, "lora")
    w.add_float32(gguf.Keys.Adapter.LORA_ALPHA, alpha)
    for (layer, proj), (a, b) in sorted(pairs.items()):
        if proj not in PROJ:
            sys.exit(f"can't map {proj} to GGUF")
        name = f"blk.{layer}.{PROJ[proj]}.weight"
        w.add_tensor(name + ".lora_a", np.ascontiguousarray(a, dtype=np.float32))
        w.add_tensor(name + ".lora_b", np.ascontiguousarray(b, dtype=np.float32))
    w.write_header_to_file(); w.write_kv_data_to_file(); w.write_tensors_to_file(); w.close()
    return out


def up():
    try:
        urllib.request.urlopen(URL + "/api/version", timeout=3)
        return True
    except OSError:
        return False


def build():
    """(Re)create Ollama model `footprint` from the active adapter. Base model alone if none yet."""
    if not shutil.which("ollama"):
        sys.exit("Ollama not found. install: https://ollama.com/download  (mac: brew install ollama)")
    if not up():
        sys.exit(f"Ollama not running at {URL}. start the Ollama app, or: ollama serve")
    b = base()
    subprocess.run(["ollama", "pull", b], check=True)
    lines = [f"FROM {b}"]
    v = config.active_version()  # not config.ADAPTERS: that is fixed at import, stale after `adapter use`
    path = os.path.join(config.MODEL_ADAPTERS, v or "none")
    if any(os.path.exists(os.path.join(path, f)) for f in ("adapters.safetensors", "adapter_model.safetensors")):
        lines.append(f"ADAPTER {export(path)}")
        what = f"adapter {v}"
    else:
        what = "no adapter yet (base model; run train)"
    mf = os.path.join(config.MODEL_ADAPTERS, "Modelfile")
    os.makedirs(config.MODEL_ADAPTERS, exist_ok=True)
    open(mf, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    subprocess.run(["ollama", "create", NAME, "-f", mf], check=True)
    print(f"ollama model '{NAME}' = {b} + {what}\nOpenAI-compatible API: {URL}/v1  (model name: {NAME})")


def refresh():
    """After the live adapter changes: rebuild `footprint` if Ollama is there, else say how."""
    if shutil.which("ollama") and up():
        build()
    else:
        print("Ollama not running: start it, then `footprint install` to serve the new adapter")


if __name__ == "__main__":  # self-check: MLX and PEFT adapters both export to the same GGUF tensors
    import tempfile, numpy as np
    from safetensors.numpy import save_file
    import gguf
    a, b = np.random.rand(1536, 8).astype(np.float32), np.random.rand(8, 256).astype(np.float32)
    mlx, peft = tempfile.mkdtemp(), tempfile.mkdtemp()
    save_file({"model.layers.3.self_attn.k_proj.lora_a": a, "model.layers.3.self_attn.k_proj.lora_b": b},
              os.path.join(mlx, "adapters.safetensors"))
    json.dump({"lora_parameters": {"rank": 8, "scale": 2.0}}, open(os.path.join(mlx, "adapter_config.json"), "w"))
    save_file({"base_model.model.model.layers.3.self_attn.k_proj.lora_A.weight": a.T.copy(),
               "base_model.model.model.layers.3.self_attn.k_proj.lora_B.weight": b.T.copy()},
              os.path.join(peft, "adapter_model.safetensors"))
    json.dump({"lora_alpha": 16}, open(os.path.join(peft, "adapter_config.json"), "w"))
    got = []
    for d in (mlx, peft):
        r = gguf.GGUFReader(export(d))
        t = {x.name: x for x in r.tensors}
        assert set(t) == {"blk.3.attn_k.weight.lora_a", "blk.3.attn_k.weight.lora_b"}, set(t)
        assert list(t["blk.3.attn_k.weight.lora_a"].shape) == [1536, 8]  # ggml ne: [in, r]
        assert list(t["blk.3.attn_k.weight.lora_b"].shape) == [8, 256]   # ggml ne: [r, out]
        assert r.fields[gguf.Keys.Adapter.LORA_ALPHA].parts[-1][0] == 16.0
        got.append(np.array(t["blk.3.attn_k.weight.lora_a"].data))
    assert np.allclose(got[0], got[1])
    os.environ["FOOTPRINT_OLLAMA_BASE"] = ""
    config.MODEL = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"; assert base() == "qwen2.5-coder:7b"
    print("ok")
