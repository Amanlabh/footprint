"""footprint — learn a local SLM from your Claude Code transcripts.

Commands:
  setup                 create .venv + install the platform backend (mlx / torch)
  trace                 arm tracing: sessions from now on become training data (run before chatting)
  collect [project]     parse ~/.claude/projects transcripts -> data/{train,valid}.jsonl
  train                 LoRA fine-tune base model on collected data
  serve                 OpenAI-compatible API at localhost:8399 (install runs this for you)
  install               auto-start server (launchd / systemd / Task Scheduler) + OpenCode /footprint
  status                what's collected/trained
  login                 GitHub device-flow sign in (personal environment)
  key new|list|revoke   manage API keys (hashes stored in your footprint-vault repo)
  sync push|pull        sync data/ + adapters/ across devices via your vault
"""
import os, sys

from . import config, service, transcripts, vault
from .backends import get


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"
    if cmd == "train" and not os.path.exists(os.path.join(config.DATA, "train.jsonl")):
        sys.exit("no data. run: footprint collect")
    {"collect": lambda: transcripts.collect(argv[1] if len(argv) > 1 else None),
     "trace": service.trace,
     "train": lambda: get().train(),
     "serve": lambda: get().serve(),
     "install": service.install,
     "status": service.status,
     "setup": service.setup,
     "login": vault.login,
     "key": lambda: vault.keys_cmd(argv[1:]),
     "sync": lambda: vault.sync_cmd(argv[1:])}.get(cmd, lambda: sys.exit(__doc__))()
