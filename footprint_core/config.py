import glob, json, math, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ADAPTER_ROOT = os.path.join(ROOT, "adapters")
PROJECTS = os.path.expanduser("~/.claude/projects")
TRACE_MARK = os.path.expanduser("~/.claude/footprint-trace")
OPENCODE = os.path.expanduser("~/.config/opencode")
OPENCODE_DB = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"),
                           "opencode", "opencode.db")
LAUNCHD = os.path.expanduser("~/Library/LaunchAgents/com.footprint.serve.plist")
SYSTEMD = os.path.expanduser("~/.config/systemd/user/footprint.service")

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"
VENV_PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe") if IS_WIN \
    else os.path.join(ROOT, ".venv", "bin", "python")
ENTRY = os.path.join(ROOT, "footprint.py")

MODEL = os.environ.get("FOOTPRINT_MODEL",
                       "mlx-community/Qwen2.5-Coder-1.5B-Instruct-4bit" if IS_MAC
                       else "Qwen/Qwen2.5-Coder-1.5B-Instruct")
PORT = os.environ.get("FOOTPRINT_PORT", "8399")
# versioned adapters: adapters/<model>/vN/ + an `active` file naming the live one (switch = rollback)
MODEL_ADAPTERS = os.path.join(ADAPTER_ROOT, re.sub(r"[^\w.-]+", "--", MODEL))


def active_version():
    try:
        return open(os.path.join(MODEL_ADAPTERS, "active"), encoding="utf-8").read().strip() or None
    except OSError:
        return None


ADAPTERS = os.path.join(MODEL_ADAPTERS, active_version() or "none")  # what serve/eval use
LORA_RANK = int(os.environ.get("FOOTPRINT_LORA_RANK", "16"))
LORA_ALPHA = 2 * LORA_RANK
LEARNING_RATE = os.environ.get("FOOTPRINT_LR", "1e-4")
ITERS = os.environ.get("FOOTPRINT_ITERS")        # unset -> auto, epoch-based (resolve_iters)
EPOCHS = float(os.environ.get("FOOTPRINT_EPOCHS", "2"))  # 1-2 passes; best checkpoint by val loss = early stop
BATCH = int(os.environ.get("FOOTPRINT_BATCH", "1"))
ITERS_CAP = int(os.environ.get("FOOTPRINT_ITERS_CAP", "2000"))  # ceiling so big datasets stay tractable
TEST_BATCHES = int(os.environ.get("FOOTPRINT_TEST_BATCHES", "25"))  # eval subsample; -1 = whole test split
# LoRA on the last N layers: late layers carry style/decisions, half the layers ~ half the backward pass.
# "half" (default) | "all" | a number
LORA_LAYERS = os.environ.get("FOOTPRINT_LORA_LAYERS", "half")
# grad checkpointing: same weights, less memory, ~20-30% slower. auto = off unless the model is big for this
# machine's RAM; an out-of-memory crash retries with it on (resuming from the last checkpoint)
GRAD_CKPT = os.environ.get("FOOTPRINT_GRAD_CKPT", "auto")
MIN_EVAL = int(os.environ.get("FOOTPRINT_MIN_EVAL", "10"))  # valid/test smaller than this = loss is noise, no early stop
SEQ_MIN, SEQ_MAX = 512, 4096  # max seq length is fitted to the longest lesson in YOUR data, within these bounds
CTX_BUDGET = 6000      # chars of history per training example
RESULT_CAP = 1500      # chars kept per tool result
CONTEXT_CAP = int(os.environ.get("FOOTPRINT_CONTEXT_CAP", "4000"))  # chars injected at session start (~1k tokens)
CONTEXT_MAX_AGE_H = float(os.environ.get("FOOTPRINT_CONTEXT_MAX_AGE_H", "168"))  # older previous session = stale, skip
MEMORY_CAP = int(os.environ.get("FOOTPRINT_MEMORY_CAP", "1500"))  # chars of similar past work injected per prompt
PROFILE_CAP = int(os.environ.get("FOOTPRINT_PROFILE_CAP", "1500"))  # chars of profile + project memory at session start
EMBED_MODEL = os.environ.get("FOOTPRINT_EMBED_MODEL", "nomic-embed-text")  # Ollama; absent = BM25-only recall
OLLAMA_URL = os.environ.get("FOOTPRINT_OLLAMA_URL", "http://localhost:11434")
# lite plan: one markdown file per project IS the context layer (no per-prompt recall). Set by `context install --lite`
PLAN_FILE = os.path.expanduser("~/.footprint/plan")
CONTEXT_MD_CAP = int(os.environ.get("FOOTPRINT_CONTEXT_MD_CAP", "8000"))  # chars of the .md printed (tail kept)
CONTEXT_MD = os.path.expanduser(os.environ.get("FOOTPRINT_CONTEXT_MD", "~/.footprint/context"))


def lite():
    if os.environ.get("FOOTPRINT_PLAN"):
        return os.environ["FOOTPRINT_PLAN"] == "lite"
    try:
        return open(PLAN_FILE, encoding="utf-8").read().strip() == "lite"
    except OSError:
        return False

SYSTEM = ("You are footprint, a local coding agent. Use the provided tools to read, search, edit and run code "
          "in the user's project, then reply briefly with what you did.")
# OpenCode's own tool names + argument names: what the model is called with at runtime, so it trains on them
_t = lambda name, desc, props, req: {"type": "function", "function": {
    "name": name, "description": desc, "parameters": {"type": "object", "properties": props, "required": req}}}
_s = {"type": "string"}
TOOLS = [_t("bash", "Run a shell command", {"command": _s, "description": _s, "timeout": {"type": "number"}}, ["command"]),
         _t("read", "Read a file", {"filePath": _s, "offset": {"type": "number"}, "limit": {"type": "number"}}, ["filePath"]),
         _t("edit", "Replace text in a file", {"filePath": _s, "oldString": _s, "newString": _s,
                                               "replaceAll": {"type": "boolean"}}, ["filePath", "oldString", "newString"]),
         _t("write", "Write a whole file", {"filePath": _s, "content": _s}, ["filePath", "content"]),
         _t("grep", "Search file contents", {"pattern": _s, "path": _s, "include": _s}, ["pattern"]),
         _t("glob", "Find files by pattern", {"pattern": _s, "path": _s}, ["pattern"])]


def has_adapter():
    return active_version() is not None and any(os.path.exists(os.path.join(ADAPTERS, f))
               for f in ("adapters.safetensors", "adapter_model.safetensors"))


def ensure_test():
    """Path to the held-out test set (newest sessions, written by collect, never trained or validated on)."""
    test = os.path.join(DATA, "test.jsonl")
    if not os.path.exists(test):
        sys.exit("no test data. run: footprint collect")
    return test


def resolve_iters():
    """Training steps. FOOTPRINT_ITERS overrides; else EPOCHS passes over the
    train set (batch-1 => 1 step/example), clamped to [100, ITERS_CAP].
    Fixed 300 iters saw <1 epoch of a few-thousand-example set — this scales."""
    if ITERS:
        return str(ITERS)
    tr = os.path.join(DATA, "train.jsonl")
    n = sum(1 for _ in open(tr)) if os.path.exists(tr) else 0
    return str(max(100, min(ITERS_CAP, math.ceil(EPOCHS * n / max(BATCH, 1)))))


def model_config():
    """config.json of the base model from the Hugging Face cache ({} if not downloaded yet)."""
    hub = os.path.join(os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")), "hub")
    for p in glob.glob(os.path.join(hub, "models--" + MODEL.replace("/", "--"), "snapshots", "*", "config.json")):
        try:
            return json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {}


def lora_layers(total):
    """How many (last) layers get LoRA. total = the model's layer count (None if unknown -> all)."""
    if LORA_LAYERS == "all" or not total:
        return total or -1
    if LORA_LAYERS == "half":
        return max(1, total // 2)
    return max(1, min(total, int(LORA_LAYERS)))


def fit_seq(lengths):
    """Max sequence length = longest lesson (tokens) rounded up to 256, within [SEQ_MIN, SEQ_MAX].
    Fitted per person: nothing is cut, and no step pays for room nobody uses."""
    top = max(lengths, default=SEQ_MAX)
    return max(SEQ_MIN, min(SEQ_MAX, -(-top // 256) * 256))


def ntok(r):
    """Token count of an apply_chat_template(tokenize=True) result. transformers 4 returns a list of ids;
    transformers 5 returns a BatchEncoding (len() == 2 = its keys, which made every lesson look 2 tokens long)."""
    if hasattr(r, "keys"):
        r = r["input_ids"]
    if len(r) and isinstance(r[0], (list, tuple)):  # batched: [[ids]]
        r = r[0]
    return len(r)


MAX_SEQ = os.environ.get("FOOTPRINT_MAX_SEQ")  # force a max length (tokens); unset = from RAM (seq_cap)
RAM_SHARE = float(os.environ.get("FOOTPRINT_RAM_SHARE", "0.55"))  # share of RAM one training step may use


def seq_cap(cfg=None, ram=None):
    """Longest lesson (tokens) this machine can train on without swapping, grad checkpointing on.
    Peak memory ~ weights + output scores: seq x vocab x 4 bytes x ~3 copies (logits, softmax, gradient).
    Checked against a real run: 1.5B-4bit, seq 2765 -> 6.0 GB predicted, 6.1 GB measured (16 GB M2).
    8 GB M1 at seq 4096 -> 8.4 GB predicted: swapped, 0 steps in 8 min. ponytail: RAM_SHARE 0.55 is a
    first guess for small machines; a loss that only scores the answer tokens would lift this cap ~15x."""
    if MAX_SEQ:
        return max(SEQ_MIN, int(MAX_SEQ))
    ram = ram if ram is not None else ram_gb()
    if not ram:
        return SEQ_MAX
    cfg = cfg if cfg is not None else model_config()
    m = re.search(r"(\d+(?:\.\d+)?)[bB]\b", MODEL)
    weights = float(m.group(1)) * (0.6 if re.search(r"4-?bit|q4", MODEL, re.I) else 2.0) if m else 2.0
    per_tok = cfg.get("vocab_size", 152000) * 4 * 3 / 1e9  # GB per token of sequence
    fit = int((RAM_SHARE * ram - weights) / per_tok)
    return max(SEQ_MIN, min(SEQ_MAX, fit // 256 * 256))


def trim(messages, count, cap):
    """Shorten one lesson to <= cap tokens by dropping the OLDEST context; the answer (last message), the
    system prompt and the ask it answers (last user message) are never cut. An assistant turn goes together
    with its tool results, so no result is left without its call. -> messages, or None if even
    system + ask + answer don't fit. count(messages) -> tokens."""
    if count(messages) <= cap:
        return messages
    head, ctx, answer = messages[:1], messages[1:-1], messages[-1:]
    blocks = []  # a user message | an assistant message + the tool results that follow it
    for m in ctx:
        if m["role"] == "tool" and blocks:
            blocks[-1].append(m)
        else:
            blocks.append([m])
    ask = max((i for i, b in enumerate(blocks) if b[0]["role"] == "user"), default=None)
    if ask is None:
        return None
    blocks = blocks[ask:]  # everything before the ask goes first (older turns)
    while True:
        out = head + [m for b in blocks for m in b] + answer
        if count(out) <= cap:
            return out
        if len(blocks) == 1:
            return None
        del blocks[1]  # then the oldest steps of this turn, right after the ask


def ram_gb():
    try:
        if IS_MAC:
            import subprocess
            return int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 1e9
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (OSError, ValueError, AttributeError):
        return None


def train_mem_gb(seq, layers, cfg=None):
    """Rough peak training memory WITHOUT grad checkpointing (GB): weights + output logits (seq x vocab,
    fp32, ~3 copies for softmax + grads) + activations kept for the backward pass of the LoRA layers.
    Calibrated on Qwen2.5-1.5B-4bit, seq 2816, 14 layers: ~9.7 GB estimated, OOM on a 16 GB M2 (2026-11-12)."""
    cfg = cfg if cfg is not None else model_config()
    m = re.search(r"(\d+(?:\.\d+)?)[bB]\b", MODEL)
    weights = float(m.group(1)) * (0.6 if re.search(r"4-?bit|q4", MODEL, re.I) else 2.0) if m else 2.0
    logits = seq * cfg.get("vocab_size", 152000) * 4 * 3 / 1e9
    acts = max(layers, 1) * seq * cfg.get("hidden_size", 2048) * 60 / 1e9
    return weights + logits + acts


def grad_ckpt(seq=SEQ_MAX, layers=None):
    """auto: on when the no-checkpoint estimate is over half of RAM (GPU gets ~2/3 of unified memory on Macs,
    minus the OS and apps). An OOM crash still flips it on and resumes, if the estimate is ever wrong."""
    if GRAD_CKPT in ("on", "off"):
        return GRAD_CKPT == "on"
    ram, cfg = ram_gb(), model_config()
    if not ram:
        return True
    return train_mem_gb(seq, layers or cfg.get("num_hidden_layers", 28), cfg) > 0.5 * ram


OOM = re.compile(r"out of memory|insufficient memory|unable to allocate|outofmemory", re.I)


if __name__ == "__main__":  # sanity: ITERS override + clamp/epoch math
    assert fit_seq([1387, 2765]) == 2816 and fit_seq([100]) == 512 and fit_seq([9000]) == 4096 and fit_seq([]) == 4096
    assert ntok([1, 2, 3]) == 3 and ntok({"input_ids": [1, 2, 3], "attention_mask": [1, 1, 1]}) == 3  # transformers 4 / 5
    assert ntok({"input_ids": [[1, 2, 3, 4]], "attention_mask": [[1] * 4]}) == 4
    _c = {"vocab_size": 151936}
    assert seq_cap(_c, ram=8.0) == 1792 and seq_cap(_c, ram=17.2) == 4096 and seq_cap(_c, ram=None) == 4096, seq_cap(_c, ram=8.0)
    _n = lambda ms: sum(len(m["content"]) for m in ms)
    _m = lambda r, n, **k: {"role": r, "content": "x" * n, **k}
    _l = [_m("system", 10), _m("user", 100), _m("assistant", 100), _m("user", 50), _m("assistant", 200), _m("tool", 300),
          _m("assistant", 100), _m("tool", 100), _m("assistant", 40)]
    assert trim(_l, _n, 2000) is _l
    assert [m["content"] for m in trim(_l, _n, 850)] == [m["content"] for m in _l[:1] + _l[3:]]   # older turn dropped
    _t = trim(_l, _n, 400)  # then the oldest call + its result, together
    assert [(m["role"], len(m["content"])) for m in _t] == [("system", 10), ("user", 50), ("assistant", 100), ("tool", 100), ("assistant", 40)]
    assert [len(m["content"]) for m in trim(_l, _n, 100)] == [10, 50, 40] and trim(_l, _n, 99) is None  # ask + answer always whole
    assert lora_layers(28) == 14 and lora_layers(None) == -1
    globals()["LORA_LAYERS"] = "all"; assert lora_layers(28) == 28
    globals()["LORA_LAYERS"] = "8"; assert lora_layers(28) == 8
    globals()["ITERS"] = "42"; assert resolve_iters() == "42"
    _f = lambda n: max(100, min(2000, math.ceil(3.0 * n / 1)))
    assert _f(5713) == 2000   # big set hits cap
    assert _f(200) == 600     # mid set = 3 epochs
    assert _f(5) == 100       # tiny set floored
    print("resolve_iters clamp/epoch math ok")
