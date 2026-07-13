import os, sys

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
ITERS = os.environ.get("FOOTPRINT_ITERS", "300")
CTX_BUDGET = 6000      # chars of history per training example
RESULT_CAP = 1500      # chars kept per tool result

SYSTEM = ("You are footprint, a local coding agent trained on Claude Code sessions. "
          "To act, emit tool calls as <tool name=\"NAME\">{json args}</tool>. "
          "Say DONE when the task is complete.")


def has_adapter():
    return any(os.path.exists(os.path.join(ADAPTERS, f))
               for f in ("adapters.safetensors", "adapter_model.safetensors"))
