"""footprint — learn a local SLM from your Claude Code transcripts.

Commands:
  setup                 create .venv + install the platform backend (mlx / torch)
  trace                 arm tracing: sessions from now on become training data (run before chatting)
  collect [project]     curated training data: accepted turns only, redacted, split by session -> data/{train,valid,test}.jsonl
  train                 LoRA fine-tune base model on collected data
  eval                  test loss + perplexity of the footprint adapter on held-out data
  serve                 OpenAI-compatible API at localhost:8399 (install runs this for you)
  install               auto-start server (launchd / systemd / Task Scheduler) + OpenCode /footprint
  context [install]     previous Claude session's state for this project; install = SessionStart hook
  bench [harvest|run|upload]  Claude-parity benchmark on your own tasks (any model)
  recall [text|--embed] similar past tasks from all your sessions (hook: added to each prompt); --embed = index all for semantic search
  profile               what new sessions learn about you + this project (also part of `context`)
  recall [text]         similar past tasks from all your sessions (hook: added to each prompt)
  facts [--all]         structured memory: your stated preferences as JSON (hook: added at session start)
  switch [list|session] open latest (or chosen) Claude Code chat in OpenCode, full history; list = show ids
  status                what's collected/trained
  login [fp_key]        sign in with your website API key (no key = GitHub device flow)
  key list|revoke       list/revoke API keys (generate them on the website)
  sync push|pull [--with-data]  sync adapters/ (and, only if asked, training data/) via your vault
"""
import os, sys

from . import bench, config, context, memory, service, switch, transcripts, vault
from .backends import get


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "status"
    if cmd == "train" and not os.path.exists(os.path.join(config.DATA, "train.jsonl")):
        sys.exit("no data. run: footprint collect")
    {"collect": lambda: transcripts.collect(argv[1] if len(argv) > 1 else None),
     "trace": service.trace,
     "train": lambda: get().train(),
     "eval": lambda: get().evaluate(),
     "serve": lambda: get().serve(),
     "install": service.install,
     "context": lambda: context.show(argv[1:]),
     "switch": lambda: switch.switch(argv[1:]),
     "recall": lambda: memory.recall(argv[1:]),
     "profile": lambda: print(memory.profile(memory.build(), os.getcwd()) or "nothing learned yet"),
     "facts": lambda: memory.facts_cmd(argv[1:]),
     "bench": lambda: bench.main(argv[1:]),
     "status": service.status,
     "setup": service.setup,
     "login": lambda: vault.login(argv[1:]),
     "key": lambda: vault.keys_cmd(argv[1:]),
     "sync": lambda: vault.sync_cmd(argv[1:])}.get(cmd, lambda: sys.exit(__doc__))()
