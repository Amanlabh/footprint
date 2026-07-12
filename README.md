# footprint

Your Claude, learned locally. Footprint fine-tunes a small local model on your
own Claude Code sessions and serves it as an OpenAI-compatible API — so when
your Claude quota runs out, OpenCode / Cursor / Codex keep working in the same
style, offline.

```sh
npm install -g footprint
footprint trace   # before starting claude
claude            # chat as usual — sessions are traced
footprint collect && footprint train
footprint install # always-on local server + /footprint in OpenCode
```

Full install (Windows / macOS / Linux) and usage docs: **[GUIDE.md](GUIDE.md)**

MIT licensed. Everything stays on your machine — transcripts and trained
weights never leave it.
