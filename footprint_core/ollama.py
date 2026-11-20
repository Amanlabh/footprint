"""Serve through Ollama: LoRA adapter baked into Ollama's own base GGUF -> `ollama create footprint`.

  adapters/<model>/vN/adapters.safetensors (MLX)  or  adapter_model.safetensors (PEFT, torch backend)
    + Ollama's base model file (e.g. qwen2.5-coder:1.5b, Q4_K_M)
    -> vN/footprint.gguf: base with W += scale * B@A on the trained layers only (those -> Q8_0;
       every other tensor and all metadata copied unchanged)
    -> Modelfile: FROM vN/footprint.gguf + the base's TEMPLATE/SYSTEM
    -> model "footprint" at http://127.0.0.1:11434/v1  (Ollama runs itself: app / brew service / systemd)

Why not `ADAPTER vN/adapter.gguf`: newer Ollama refuses it ("LoRA adapters are no longer supported").
Why copy TEMPLATE: a model created FROM a .gguf file otherwise gets the raw template inside the file,
so replies never stop and tool calls come back as plain text.
"""
import json, os, re, shutil, subprocess, sys, urllib.request

from . import config

URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if "://" not in URL:
    URL = "http://" + URL
NAME = "footprint"
KEEP = os.environ.get("FOOTPRINT_KEEP_ALIVE", "30m")  # unload after this idle; reload = re-read whole chat
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


def merge(path, base_gguf, out=None):
    """Bake the adapter in <path> into base_gguf -> <path>/footprint.gguf (or out). -> its path.
    Only the LoRA'd tensors are rewritten (dequantize, add scale*B@A, requantize to Q8_0)."""
    try:
        import gguf, numpy as np
        from gguf import quants, GGMLQuantizationType as Q, GGUFValueType as V
    except ImportError:
        sys.exit("missing the gguf package (needed to hand the model to Ollama). run: footprint setup")
    pairs, alpha = _lora(path)
    if not pairs:
        sys.exit(f"no LoRA tensors in {path}")
    delta = {}
    for (layer, proj), (a, b) in pairs.items():  # a [r,in], b [out,r]; llama.cpp/PEFT scale = alpha/r
        if proj not in PROJ:
            sys.exit(f"can't map {proj} to GGUF")
        delta[f"blk.{layer}.{PROJ[proj]}.weight"] = (a, b, alpha / a.shape[0])
    out = out or os.path.join(path, "footprint.gguf")
    r = gguf.GGUFReader(base_gguf)
    w = gguf.GGUFWriter(out + ".part", r.fields["general.architecture"].contents())
    for name, f in r.fields.items():
        if name.startswith("GGUF.") or name == "general.architecture":
            continue  # the writer adds these itself
        vt = f.types[0]
        w.add_key_value(name, f.contents(), vt, sub_type=f.types[-1] if vt == V.ARRAY else None)
    for t in r.tensors:
        if t.name in delta:
            a, b, s = delta.pop(t.name)
            W = quants.dequantize(t.data, t.tensor_type).astype(np.float32)
            d = s * (b.astype(np.float32) @ a.astype(np.float32))
            if W.shape != d.shape:
                sys.exit(f"adapter doesn't fit {t.name}: {d.shape} vs base {W.shape}. wrong FOOTPRINT_OLLAMA_BASE?")
            w.add_tensor(t.name, quants.quantize(W + d, Q.Q8_0), raw_dtype=Q.Q8_0)
        else:
            w.add_tensor(t.name, t.data, raw_dtype=t.tensor_type)
    if delta:
        sys.exit(f"base has no tensor {next(iter(delta))}. wrong FOOTPRINT_OLLAMA_BASE?")
    w.write_header_to_file(); w.write_kv_data_to_file(); w.write_tensors_to_file(); w.close()
    os.replace(out + ".part", out)
    return out


def _show(tag):
    return subprocess.run(["ollama", "show", tag, "--modelfile"], capture_output=True, text=True, check=True).stdout


def base_file(tag):
    """Path of the GGUF blob behind an Ollama tag (its Modelfile's FROM line)."""
    m = re.search(r"^FROM (\S+\.gguf|/\S+)$", _show(tag), re.M)
    if not m or not os.path.exists(m[1]):
        sys.exit(f"can't find the model file behind {tag}. try: ollama pull {tag}")
    return m[1]


def chat_format(tag):
    """The base's TEMPLATE ... SYSTEM block, so the merged model chats (and stops, and calls tools) like it."""
    return _template(_show(tag))


def _template(modelfile):
    m = re.search(r"^TEMPLATE .*?(?=^PARAMETER |^LICENSE |^MESSAGE |\Z)", modelfile, re.M | re.S)
    return m[0].rstrip() if m else ""


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
    # OpenCode's first prompt (system + tools) is ~12k tokens: Ollama's default 4096 truncates it, and a
    # truncated prompt never hits the prefix cache (every turn re-reads everything). KV for 32k ~0.9 GB.
    ctx = int(os.environ.get("FOOTPRINT_NUM_CTX") or (32768 if (config.ram_gb() or 0) >= 15 else 16384))
    v = config.active_version()  # not config.ADAPTERS: that is fixed at import, stale after `adapter use`
    path = os.path.join(config.MODEL_ADAPTERS, v or "none")
    weights = [os.path.join(path, f) for f in ("adapters.safetensors", "adapter_model.safetensors")]
    weights = [f for f in weights if os.path.exists(f)]
    if weights:
        out = os.path.join(path, "footprint.gguf")
        if not os.path.exists(out) or os.path.getmtime(out) < os.path.getmtime(weights[0]):
            print(f"baking adapter {v} into {b}…")
            merge(path, base_file(b), out)
        lines = [f"FROM {out}", chat_format(b)]
        what = f"adapter {v}"
    else:
        lines = [f"FROM {b}"]
        what = "no adapter yet (base model; run train)"
    lines.append(f"PARAMETER num_ctx {ctx}")
    mf = os.path.join(config.MODEL_ADAPTERS, "Modelfile")
    os.makedirs(config.MODEL_ADAPTERS, exist_ok=True)
    open(mf, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    subprocess.run(["ollama", "create", NAME, "-f", mf], check=True)
    warm()
    print(f"ollama model '{NAME}' = {b} + {what}\nOpenAI-compatible API: {URL}/v1  (model name: {NAME})")


def warm():
    """Load `footprint` now and keep it KEEP after the last ping (the /v1 API can't set keep_alive)."""
    try:
        urllib.request.urlopen(urllib.request.Request(URL + "/api/generate", json.dumps(
            {"model": NAME, "keep_alive": KEEP}).encode()), timeout=120)
    except OSError as e:
        print(f"(could not preload {NAME}: {e})")


def unload():
    """Free the GPU memory Ollama holds for `footprint` (training next to a loaded model runs out of memory)."""
    if shutil.which("ollama") and up():
        subprocess.run(["ollama", "stop", NAME], capture_output=True)


def refresh():
    """After the live adapter changes: rebuild `footprint` if Ollama is there, else say how."""
    if shutil.which("ollama") and up():
        build()
    else:
        print("Ollama not running: start it, then `footprint install` to serve the new adapter")


if __name__ == "__main__":  # self-check: MLX and PEFT adapters both bake into a base GGUF the same way
    import tempfile, numpy as np
    from safetensors.numpy import save_file
    import gguf
    from gguf import quants, GGMLQuantizationType as Q
    rng = np.random.default_rng(0)
    a, b = rng.random((1536, 8), dtype=np.float32) * .1, rng.random((8, 256), dtype=np.float32) * .1
    W, norm = rng.standard_normal((256, 1536), dtype=np.float32), rng.random(1536, dtype=np.float32)
    tmp = tempfile.mkdtemp()
    base_gguf = os.path.join(tmp, "base.gguf")
    bw = gguf.GGUFWriter(base_gguf, "qwen2")
    bw.add_string("tokenizer.ggml.model", "gpt2"); bw.add_token_list(["a", "b", "c"]); bw.add_context_length(4096)
    bw.add_tensor("blk.3.attn_k.weight", quants.quantize(W, Q.Q8_0), raw_dtype=Q.Q8_0)
    bw.add_tensor("output_norm.weight", norm)
    bw.write_header_to_file(); bw.write_kv_data_to_file(); bw.write_tensors_to_file(); bw.close()
    W = quants.dequantize(quants.quantize(W, Q.Q8_0), Q.Q8_0)  # what the base really holds
    mlx, peft = tempfile.mkdtemp(), tempfile.mkdtemp()
    save_file({"model.layers.3.self_attn.k_proj.lora_a": a, "model.layers.3.self_attn.k_proj.lora_b": b},
              os.path.join(mlx, "adapters.safetensors"))
    json.dump({"lora_parameters": {"rank": 8, "scale": 2.0}}, open(os.path.join(mlx, "adapter_config.json"), "w"))
    save_file({"base_model.model.model.layers.3.self_attn.k_proj.lora_A.weight": a.T.copy(),
               "base_model.model.model.layers.3.self_attn.k_proj.lora_B.weight": b.T.copy()},
              os.path.join(peft, "adapter_model.safetensors"))
    json.dump({"lora_alpha": 16}, open(os.path.join(peft, "adapter_config.json"), "w"))
    want = W + 2.0 * (b.T @ a.T)  # MLX: y += scale * x@a@b, scale 2 -> W += 2 * (a@b).T
    got = []
    for d in (mlx, peft):
        r = gguf.GGUFReader(merge(d, base_gguf))
        t = {x.name: x for x in r.tensors}
        assert set(t) == {"blk.3.attn_k.weight", "output_norm.weight"}, set(t)
        k = t["blk.3.attn_k.weight"]
        assert k.tensor_type == Q.Q8_0
        merged = quants.dequantize(k.data, k.tensor_type)
        assert merged.shape == (256, 1536) and np.abs(merged - want).max() < 0.05, np.abs(merged - want).max()
        assert np.array_equal(np.array(t["output_norm.weight"].data), norm)  # untouched tensors copied as-is
        assert r.fields["tokenizer.ggml.model"].contents() == "gpt2"
        assert r.fields["tokenizer.ggml.tokens"].contents() == ["a", "b", "c"]
        assert r.fields["general.architecture"].contents() == "qwen2"
        got.append(merged)
    assert np.allclose(got[0], got[1])
    t = _template('# FROM x\nFROM /x\nTEMPLATE """{{ .Prompt }}\n"""\nSYSTEM You are Qwen.\nLICENSE """MIT"""\n')
    assert t == 'TEMPLATE """{{ .Prompt }}\n"""\nSYSTEM You are Qwen.', t
    os.environ["FOOTPRINT_OLLAMA_BASE"] = ""
    config.MODEL = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"; assert base() == "qwen2.5-coder:7b"
    print("ok")
