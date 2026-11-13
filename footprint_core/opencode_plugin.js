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
    // session memory: similar past work for this prompt, as a hidden (synthetic) part of the
    // user's message — not the system prompt, so the prompt cache stays intact.
    "chat.message": async (input, output) => {
      // footprint model in Ollama: (re)load it now and keep it 30 min past this message. Ollama's /v1
      // API ignores keep_alive, and an unload means re-reading the whole chat (~12k+ tokens) next turn.
      if (input.model?.providerID === "footprint") {
        const host = (process.env.OLLAMA_HOST || "127.0.0.1:11434").replace(/^(?!https?:\/\/)/, "http://")
        fetch(host + "/api/generate", {
          method: "POST",
          body: JSON.stringify({ model: input.model.modelID, keep_alive: process.env.FOOTPRINT_KEEP_ALIVE || "30m" }),
        }).catch(() => {})
      }
      const prompt = output.parts
        .filter((p) => p.type === "text" && !p.synthetic)
        .map((p) => p.text)
        .join("\n")
        .trim()
      if (!prompt || !output.parts.length) return
      const r = spawnSync(PY, [ENTRY, "recall"], {
        input: JSON.stringify({ cwd: directory, session_id: input.sessionID, prompt }),
        encoding: "utf-8",
        timeout: 10000,
      })
      const memo = r.status === 0 ? (r.stdout || "").trim() : ""
      if (!memo) return
      // OpenCode ids: "prt_" + 12 ascending hex + 14 random; +1 sorts right after the user's text
      const last = output.parts.map((p) => p.id).sort().pop()
      const hex = (BigInt("0x" + last.slice(4, 16)) + 1n).toString(16).padStart(12, "0")
      const abc = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
      const rand = Array.from({ length: 14 }, () => abc[Math.floor(Math.random() * 62)]).join("")
      output.parts.push({
        id: `prt_${hex}${rand}`,
        sessionID: input.sessionID,
        messageID: output.message.id,
        type: "text",
        text: memo,
        synthetic: true,
      })
    },
  }
}
