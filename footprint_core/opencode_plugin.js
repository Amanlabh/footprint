// footprint: new OpenCode sessions start where the last session in this project
// (Claude Code or OpenCode) left off. Installed by `footprint context install`.
import { spawnSync } from "node:child_process"

const PY = __PY__
const ENTRY = __ENTRY__

export const Footprint = async ({ directory }) => {
  const fresh = new Set() // sessions created while this OpenCode runs: only these get context
  const cache = new Map() // computed once per session -> identical system prompt every turn (prompt-cache friendly)
  return {
    event: async ({ event }) => {
      const info = event.type === "session.created" && event.properties?.info
      if (info && !info.parentID) fresh.add(info.id) // skip subagent sessions
    },
    "experimental.chat.system.transform": async (input, output) => {
      const id = input.sessionID
      if (!id || !fresh.has(id)) return
      if (!cache.has(id)) {
        const r = spawnSync(PY, [ENTRY, "context"], {
          input: JSON.stringify({ cwd: directory, session_id: id }),
          encoding: "utf-8",
          timeout: 10000,
        })
        cache.set(id, r.status === 0 ? (r.stdout || "").trim() : "")
      }
      if (cache.get(id)) output.system.push(cache.get(id))
    },
  }
}
