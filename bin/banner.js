#!/usr/bin/env node
console.log(`
\x1b[36m███████╗ ██████╗  ██████╗ ████████╗██████╗ ██████╗ ██╗███╗   ██╗████████╗
██╔════╝██╔═══██╗██╔═══██╗╚══██╔══╝██╔══██╗██╔══██╗██║████╗  ██║╚══██╔══╝
█████╗  ██║   ██║██║   ██║   ██║   ██████╔╝██████╔╝██║██╔██╗ ██║   ██║
██╔══╝  ██║   ██║██║   ██║   ██║   ██╔═══╝ ██╔══██╗██║██║╚██╗██║   ██║
██║     ╚██████╔╝╚██████╔╝   ██║   ██║     ██║  ██║██║██║ ╚████║   ██║
╚═╝      ╚═════╝  ╚═════╝    ╚═╝   ╚═╝     ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝\x1b[0m

  your Claude, learned locally.

  1. footprint trace      arm tracing — do this BEFORE starting claude
  2. claude               chat as usual; every session is traced automatically
  3. footprint collect    turn traced sessions into training data
  4. footprint train      fine-tune the local model
  5. footprint install    always-on server + /footprint command in OpenCode

  Claude quota over? open OpenCode, type /footprint <task> — works like Claude.
`);
