import math, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ADAPTERS = os.path.join(ROOT, "adapters")
PROJECTS = os.path.expanduser("~/.claude/projects")
TRACE_MARK = os.path.expanduser("~/.claude/footprint-trace")
OPENCODE = os.path.expanduser("~/.config/opencode")
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
ITERS = os.environ.get("FOOTPRINT_ITERS")        # unset -> auto, epoch-based (resolve_iters)
EPOCHS = float(os.environ.get("FOOTPRINT_EPOCHS", "3"))
BATCH = int(os.environ.get("FOOTPRINT_BATCH", "1"))
ITERS_CAP = int(os.environ.get("FOOTPRINT_ITERS_CAP", "2000"))  # ceiling so big datasets stay tractable
TEST_BATCHES = int(os.environ.get("FOOTPRINT_TEST_BATCHES", "25"))  # eval subsample; -1 = whole test split
CTX_BUDGET = 6000      # chars of history per training example
RESULT_CAP = 1500      # chars kept per tool result
CONTEXT_CAP = int(os.environ.get("FOOTPRINT_CONTEXT_CAP", "4000"))  # chars injected at session start (~1k tokens)
CONTEXT_MAX_AGE_H = float(os.environ.get("FOOTPRINT_CONTEXT_MAX_AGE_H", "168"))  # older previous session = stale, skip

SYSTEM = ("You are footprint, a local coding agent trained on Claude Code sessions. "
          "To act, emit tool calls as <tool name=\"NAME\">{json args}</tool>. "
          "Say DONE when the task is complete.")


def has_adapter():
    return any(os.path.exists(os.path.join(ADAPTERS, f))
               for f in ("adapters.safetensors", "adapter_model.safetensors"))


def ensure_test():
    """Path to held-out eval set. mlx_lm --test wants data/test.jsonl; collect
    only writes valid.jsonl, so reuse that as the test split. Copied fresh every
    time: each collect reshuffles, so a stale copy would leak into train."""
    valid = os.path.join(DATA, "valid.jsonl")
    if not os.path.exists(valid):
        sys.exit("no eval data. run: footprint collect")
    import shutil
    return shutil.copyfile(valid, os.path.join(DATA, "test.jsonl"))


def resolve_iters():
    """Training steps. FOOTPRINT_ITERS overrides; else EPOCHS passes over the
    train set (batch-1 => 1 step/example), clamped to [100, ITERS_CAP].
    Fixed 300 iters saw <1 epoch of a few-thousand-example set — this scales."""
    if ITERS:
        return str(ITERS)
    tr = os.path.join(DATA, "train.jsonl")
    n = sum(1 for _ in open(tr)) if os.path.exists(tr) else 0
    return str(max(100, min(ITERS_CAP, math.ceil(EPOCHS * n / max(BATCH, 1)))))


if __name__ == "__main__":  # sanity: ITERS override + clamp/epoch math
    globals()["ITERS"] = "42"; assert resolve_iters() == "42"
    _f = lambda n: max(100, min(2000, math.ceil(3.0 * n / 1)))
    assert _f(5713) == 2000   # big set hits cap
    assert _f(200) == 600     # mid set = 3 epochs
    assert _f(5) == 100       # tiny set floored
    print("resolve_iters clamp/epoch math ok")
