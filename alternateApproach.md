# footprint — Alternate Approaches & GTM

How should footprint turn a user's Claude sessions into a model that keeps working "like Claude" — and what do we sell?

Written 2026-11-02. Benchmarks and prices move fast — re-check sources before committing money.

---

## TL;DR

- **Per-user LoRA on hosted inference: possible** (multi-LoRA serving) — but **not on OpenRouter**. Together, Fireworks, or self-hosted vLLM.
- **No laptop model reaches Claude Opus 5.5.** LoRA on one user's sessions teaches *style & habits*, not *capability*.
- **Recommended GTM:** continuity free (works with any model, $0 to us) → local model as optional *privacy* feature → hosted **per-team** LoRA as the paid/enterprise tier, **only after** a task eval proves LoRA helps.
- **Strongest cheap alternative:** skip fine-tuning; turn sessions into a **learned profile** (conventions, preferences, project facts) injected into any model's context — Approach C below.

---

## Approach A — Custom (hosted) inference with per-user LoRA

### Is a unique LoRA per user possible? **Yes.**

**Multi-LoRA serving:** one base model on the GPU, thousands of small adapters (~10–200MB each) hot-swapped per request. A request names its adapter (e.g. `base:user123`). Supported by vLLM, LoRAX, Ray Serve. You do **not** need a GPU per user.

| Platform | Per-user LoRA | Notes |
|---|---|---|
| **OpenRouter** | ❌ | Routes to providers' catalog models only; no adapter upload found |
| **Together AI** | ✅ | Serverless multi-LoRA: upload adapters, ~base-model token price |
| **Fireworks** | ✅ | Multi-LoRA: many adapters on one deployment, base-model token price |
| **Truefoundry** | ✅ likely | Deploys vLLM on your cloud (vLLM supports multi-LoRA); Truefoundry docs not verified |
| **Self-host** (Modal / RunPod + vLLM) | ✅ | Cheapest at scale; you operate GPUs |

### Catches
- Adapters only on **supported base models** — usually Qwen/Llama 8B–70B. LoRA on frontier-size open models (GLM-5, MiniMax, DeepSeek) often not offered.
- **Cost to us:** training per user (cheap — little data) + every inference token. Free users = pure cost.
- Session data leaves the user's machine → enterprise privacy review.

---

## Approach B — Local models + local LoRA

### The hard truth
- **Fine-tuning ≠ capability.** A 7B model trained on Claude transcripts copies how Claude *talks*, not how well it *reasons*. A few hundred sessions can't transfer capability and can even hurt it.
- **Benchmark gap:** best self-hostable coding models ≈ **60–72%** SWE-bench Verified. Server-only open models: GLM-5.2 ≈ 78.7, MiniMax M2.5 ≈ 80.2. Claude Opus 4.6 = 80.8; Opus 5.5 is higher.
- **Today footprint ships Qwen2.5-Coder-1.5B** — too weak to drive a coding agent.

### Local models by RAM (4-bit, approx.)

| Laptop RAM | Models | Agent quality | LoRA on Mac (MLX) |
|---|---|---|---|
| 8GB | Qwen2.5-Coder 1.5B/3B, Qwen3-4B | Autocomplete-level, no agent work | ✅ easy |
| 16GB | Qwen2.5-Coder-7B, Qwen3-8B | Small single-file edits | ✅ |
| 24–32GB | **Qwen3-Coder-30B-A3B** (MoE, fast), gpt-oss-20b, Devstral Small 24B, Qwen2.5-Coder-32B | Usable agent, mid-tier | ✅ (MoE ~32GB+) |
| 48–64GB | Qwen3-Coder-Next (~46GB, ~71% SWE-bench Verified) | Good, closest to frontier | ⚠️ tight, 64GB+ |
| 128GB+ | gpt-oss-120b, GLM-4.5-Air | Strong | ⚠️ slow |
| Servers only | GLM-5.x, MiniMax M2.5, DeepSeek V4, Kimi | Near-frontier | ❌ not laptop |

**Realistic target:** most dev laptops are 16–32GB → **Qwen3-Coder-30B-A3B** on 32GB, 7B fallback on 16GB. Upgrade the default from 1.5B.

### Pros / cons
- ✅ $0 to us, private, offline.
- ❌ RAM-bound; slow training on 16GB; quality well below Claude.

---

## Alternatives beyond A and B

### C — Learned profile instead of fine-tuning (recommended to try first)
Mine sessions for **what the user wants**, not weights:
- conventions (naming, test style, commit format), preferred libraries, things they always correct, project facts, recurring commands.
- Write it to a compact profile → inject via the existing handover (Claude Code hook / OpenCode plugin / `AGENTS.md`).

| ✅ | ❌ |
|---|---|
| Works with **any** model — Claude, Big Pickle, Ollama, GLM | Uses context tokens (keep it ~1–2k) |
| $0, no GPU, no RAM limit, instant | Needs a good extractor (can use the user's own model to summarize) |
| Editable & auditable by the user — enterprises like that | Not "a model of my own" as a marketing line |
| Improves the strongest models too, not just weak local ones | |

Builds directly on what exists (`context.py` already extracts goal/files/todos/errors).

### D — Router / hybrid
Local small model for cheap, frequent tasks (summaries, commit messages, simple edits, the handover itself); escalate hard tasks to a frontier model (user's Claude or free cloud model).
- ✅ cuts cost + quota use; works offline for easy stuff.
- ❌ routing heuristics are hard to get right; two models to support.

### E — BYOK (bring your own key)
User plugs their own OpenRouter / Anthropic / Gemini / Ollama-cloud key; footprint is the continuity + profile layer on top.
- ✅ $0 inference cost to us, any model, no ToS issues with reselling.
- ❌ users must get a key (friction); we don't control quality.

### F — Per-team hosted LoRA (variant of A)
One adapter per **team or repo** instead of per user → more data per adapter, better results, fewer adapters to manage. Natural enterprise product.

### G — Shared "free" gateway (what we sketched earlier)
Our key + our endpoint routing to GLM / Gemini / OpenRouter free tiers.
- ✅ zero setup for users.
- ❌ we pay or get throttled at scale; reselling free tiers may break provider terms. **Paid tiers only.**

---

## Comparison

| | Cost to us | Quality vs Claude | Privacy | Setup for user | Unique per user |
|---|---|---|---|---|---|
| A Hosted per-user LoRA | 💸 per token | Base model level | ❌ data leaves | None | ✅ |
| B Local LoRA | $0 | Low–mid (RAM) | ✅ | Big download + RAM | ✅ |
| **C Learned profile** | **$0** | **= whatever model they use** | ✅ (local) | None | ✅ |
| D Router | $0–low | Mixed | ✅ mostly | Medium | partial |
| E BYOK | $0 | Their choice | Depends | Get a key | via C |
| F Per-team LoRA | 💸 | Base model level | ❌ (org-controlled) | None | per team |
| G Shared gateway | 💸💸 | Base model level | ❌ | None | ❌ |

---

## Recommended GTM

| Tier | Offer | Cost to us |
|---|---|---|
| **Free** | Continuity (handover, `switch`, `/continue`) + **learned profile (C)** with any model — BYOK or free models (E) | $0 |
| **Free, opt-in** | Local "personal model" (B) on Qwen3-Coder-30B-A3B / 7B — sold as *offline, private, your style*, **not** a Claude replacement | $0 |
| **Paid — Team / Enterprise** | Hosted **per-team** LoRA (F) on multi-LoRA (Together / Fireworks / own vLLM) + team-synced continuity & profiles + admin, sync opt-out | per token, priced per seat |

### Gate before charging: prove it
`footprint eval` measures loss/perplexity — that is not task success. Build a **task eval**: ~20 real tasks from a user's history, scored on base vs base+profile (C) vs base+LoRA (B/A).
- LoRA clearly wins → keep A/B/F as paid differentiators.
- Profile ≈ LoRA → ship C everywhere, keep LoRA as an extra.
- Neither helps → the product is continuity; drop training.

### Next steps
1. Build the task eval (small, ~20 tasks).
2. Prototype C (learned profile) on top of `context.py`.
3. Switch local default model from Qwen2.5-Coder-1.5B → Qwen3-Coder-30B-A3B (32GB) / 7B (16GB).
4. Run eval → pick between C-only and C + LoRA.
5. Only then: hosted multi-LoRA pilot with one team.

---

## Sources
- [Together AI — serverless multi-LoRA](https://www.together.ai/blog/serverless-multi-lora-fine-tune-and-deploy-hundreds-of-adapters-for-model-customization-at-scale)
- [Fireworks vs Together](https://www.morphllm.com/comparisons/fireworks-vs-together)
- [Ray Serve multi-LoRA](https://docs.ray.io/en/latest/serve/llm/user-guides/multi-lora.html)
- [vLLM LoRA adapters](https://vllm.hexdocs.pm/lora.md)
- [Best open-source coding models 2026 (morphllm)](https://www.morphllm.com/best-open-source-coding-model-2026)
- [Self-host hardware match 2026 (digitalapplied)](https://www.digitalapplied.com/blog/best-open-weight-coding-models-self-host-hardware-match-2026)
- [Best open-source models for SWE-bench (Modal)](https://modal.com/resources/best-open-source-models-swe-bench-coding-agents)
- [Best open-source coding model (ertas)](https://www.ertas.ai/best/best-open-source-coding-model)
