import Link from "next/link";
import {
  Cpu,
  ShieldCheck,
  Wifi,
  Radio,
  Boxes,
  GitBranch,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/site/code-block";
import { VaultNote } from "@/components/site/vault-note";

const flow = ["trace", "chat with claude", "collect", "train", "install", "/footprint"];

const modules = [
  {
    icon: Cpu,
    chip: "STYLE.LORA",
    title: "Learns your style",
    body: "LoRA fine-tunes a small model on how you and Claude actually work in your projects — not a generic assistant.",
    spec: "SRC ~/.claude/projects · ADAPTER LoRA",
  },
  {
    icon: ShieldCheck,
    chip: "PRIV.GUARD",
    title: "Private by default",
    body: "Transcripts and trained weights are gitignored and never leave your machine. No upload, no telemetry.",
    spec: "NET TX 0 B · TELEMETRY NONE",
  },
  {
    icon: Wifi,
    chip: "OFFLINE.CORE",
    title: "Fully offline",
    body: "Once trained, everything runs locally. No network, no quota, no rate limit between you and your code.",
    spec: "UPLINK NONE · QUOTA ∞",
  },
  {
    icon: Radio,
    chip: "API.BRIDGE",
    title: "OpenAI-compatible",
    body: "Serves at http://127.0.0.1:8399/v1. Point Cursor, OpenCode, or Codex CLI at it and keep going.",
    spec: "PORT 0x20CF · PROTO openai/v1",
  },
  {
    icon: Boxes,
    chip: "MULTI.ARCH",
    title: "Cross-platform",
    body: "MLX backend on Apple Silicon, PyTorch everywhere else — macOS, Linux, and Windows all supported.",
    spec: "MLX arm64 · TORCH cuda/cpu",
  },
  {
    icon: GitBranch,
    chip: "ZERO.HOOK",
    title: "No tracer needed",
    body: "Claude Code already logs every session. Footprint reads those transcripts — nothing to instrument.",
    spec: "READS *.jsonl · HOOKS 0",
  },
];

const hud = [
  ["MODEL", "Qwen2.5-Coder-1.5B"],
  ["QUANT", "4-bit"],
  ["CTX", "6K"],
  ["PORT", "8399"],
  ["STATE", "SERVING"],
];

const steps = [
  { n: "01", title: "Trace", body: "Arm a marker so only sessions from now on become training data." },
  { n: "02", title: "Collect", body: "Parse transcripts into chat-format examples — prompts, replies, tool calls." },
  { n: "03", title: "Train", body: "LoRA fine-tune a small model in about ten minutes on your machine." },
  { n: "04", title: "Install", body: "An always-on local server, wired into OpenCode with a /footprint command." },
];

export default function Home() {
  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="guava-grid absolute inset-0 opacity-70" />
        <div className="guava-radial absolute inset-0" />
        <div className="relative mx-auto w-full max-w-6xl px-5 pb-20 pt-20 sm:pt-28">
          <Badge
            variant="secondary"
            className="mb-6 font-pixel text-xs tracking-wide"
          >
            local SLM · MLX + PyTorch LoRA
          </Badge>

          <h1 className="max-w-3xl text-balance text-5xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
            Your Claude, <span className="text-primary">learned locally.</span>
          </h1>

          {/* Doto accent line on the hero */}
          <p className="font-doto mt-6 max-w-2xl text-lg text-foreground/80 sm:text-xl">
            when the quota runs out, your model keeps working — in your style,
            on your machine, offline.
          </p>

          <p className="mt-5 max-w-2xl text-pretty text-base text-muted-foreground sm:text-lg">
            Footprint watches your Claude Code sessions, fine-tunes a small
            local model on how you and Claude work, and serves it
            OpenAI-compatible. Cursor, OpenCode, and Codex CLI keep going in the
            same style — fully offline.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button size="lg" render={<Link href="/docs" />}>
              Get started
              <ArrowRight className="size-4" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              render={<Link href="/how-it-works" />}
            >
              How it works
            </Button>
          </div>

          <div className="mt-12 max-w-xl">
            <CodeBlock title="install">
              <span className="text-muted-foreground">$ </span>
              npm install -g footprint-trace
            </CodeBlock>
          </div>

          <VaultNote className="mt-6" />
        </div>
      </section>

      {/* Flow strip */}
      <section className="border-y border-border/60 bg-secondary/30">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-3 gap-y-2 px-5 py-6">
          {flow.map((step, i) => (
            <div key={step} className="flex items-center gap-3">
              <span className="font-doto text-sm text-foreground/70">
                {step}
              </span>
              {i < flow.length - 1 && (
                <ArrowRight className="size-3.5 text-guava-flesh" />
              )}
            </div>
          ))}
        </div>
      </section>

      {/* System modules */}
      <section className="mx-auto w-full max-w-6xl px-5 py-20">
        <div className="guava-grid overflow-hidden rounded-3xl border border-border bg-card/60 p-6 sm:p-10">
          <div className="mb-10 max-w-2xl">
            <p className="font-mono text-xs tracking-[0.25em] text-guava-flesh">
              [ SYSTEM // MODULES ]
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              A model that already knows your project.
            </h2>
            <p className="font-doto mt-3 text-muted-foreground">
              trained on your sessions, not the whole internet.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {modules.map((m) => (
              <div
                key={m.chip}
                className="group relative rounded-lg border border-border bg-card shadow-sm transition-colors hover:border-guava-flesh/60"
              >
                {/* corner ticks */}
                <span className="pointer-events-none absolute -left-px -top-px size-2.5 border-l-2 border-t-2 border-guava-flesh/70" />
                <span className="pointer-events-none absolute -bottom-px -right-px size-2.5 border-b-2 border-r-2 border-guava-flesh/70" />

                <div className="flex items-center justify-between border-b border-border/60 px-4 py-2.5">
                  <span className="font-mono text-xs tracking-widest text-muted-foreground">
                    {m.chip}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="led size-1.5 rounded-full bg-guava-rind" />
                    <span className="font-mono text-[10px] uppercase text-guava-rind">
                      on
                    </span>
                  </span>
                </div>

                <div className="px-4 py-4">
                  <div className="flex items-center gap-2.5">
                    <m.icon className="size-4 text-guava-flesh" />
                    <h3 className="font-semibold">{m.title}</h3>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {m.body}
                  </p>
                </div>

                <div className="border-t border-dashed border-border/60 px-4 py-2">
                  <p className="truncate font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80">
                    {m.spec}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* HUD status bar */}
          <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-border bg-background/70 px-4 py-3 font-mono text-[11px]">
            {hud.map(([k, val]) => (
              <span key={k} className="flex items-center gap-2">
                <span className="text-muted-foreground">{k}</span>
                <span className="text-foreground">{val}</span>
              </span>
            ))}
            <span className="ml-auto hidden items-center gap-1.5 sm:flex">
              <span className="led size-1.5 rounded-full bg-guava-rind" />
              <span className="text-guava-rind">127.0.0.1:8399 LIVE</span>
            </span>
          </div>
        </div>
      </section>

      {/* Steps */}
      <section className="border-t border-border/60 bg-secondary/20">
        <div className="mx-auto w-full max-w-6xl px-5 py-20">
          <div className="mb-12 max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Four commands, start to finish.
            </h2>
            <p className="mt-3 text-muted-foreground">
              From your first traced session to a running local model.
            </p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map((s) => (
              <div
                key={s.n}
                className="rounded-xl border border-border/70 bg-card p-5"
              >
                <div className="font-pixel text-2xl text-guava-flesh">
                  {s.n}
                </div>
                <h3 className="mt-3 text-lg font-semibold">{s.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto w-full max-w-6xl px-5 py-24">
        <div className="relative overflow-hidden rounded-3xl border border-border bg-card px-6 py-16 text-center sm:px-12">
          <div className="guava-radial absolute inset-0 opacity-80" />
          <div className="relative">
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Keep coding when Claude clocks out.
            </h2>
            <p className="font-doto mx-auto mt-4 max-w-xl text-lg text-foreground/80">
              spin up your own model in about ten minutes.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Button size="lg" render={<Link href="/docs" />}>
                Read the docs
                <ArrowRight className="size-4" />
              </Button>
              <Button
                size="lg"
                variant="outline"
                render={
                  <a
                    href="https://github.com/Amanlabh/footprint"
                    target="_blank"
                    rel="noreferrer"
                  />
                }
              >
                Star on GitHub
              </Button>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
