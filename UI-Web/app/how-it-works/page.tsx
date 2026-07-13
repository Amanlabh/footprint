import type { Metadata } from "next";
import { CodeBlock } from "@/components/site/code-block";
import { VaultNote } from "@/components/site/vault-note";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

export const metadata: Metadata = {
  title: "How it works — footprint",
  description:
    "How footprint turns your Claude Code transcripts into a local, OpenAI-compatible model.",
};

const pipeline = [
  {
    n: "01",
    title: "Claude Code already logs everything",
    body: "Every session — your prompts, Claude's replies, and tool calls — is written to ~/.claude/projects. Footprint reads those transcripts directly, so there's no tracer or wrapper to install.",
  },
  {
    n: "02",
    title: "trace marks a starting line",
    body: "footprint trace arms a marker so only sessions from that point on become training data. Skip it (or delete the marker) to train on your entire history instead.",
  },
  {
    n: "03",
    title: "collect parses transcripts into examples",
    body: "Each assistant turn becomes a chat-format training example within a ~6k-character context window. Tool calls are encoded so the model learns your workflow, not just prose.",
  },
  {
    n: "04",
    title: "train runs a LoRA fine-tune",
    body: "A small base model (Qwen2.5-Coder-1.5B by default) is LoRA fine-tuned on your examples — about ten minutes, MLX on Apple Silicon or PyTorch + PEFT everywhere else.",
  },
  {
    n: "05",
    title: "install serves it, always on",
    body: "A launchd / systemd / Task Scheduler agent runs the server at 127.0.0.1:8399, starts at login, and restarts on crash. It also wires up OpenCode with a /footprint command.",
  },
  {
    n: "06",
    title: "Any OpenAI-compatible tool plugs in",
    body: "Point Cursor, OpenCode, or Codex CLI at the local URL. When your Claude quota runs out, they keep working in the same style — fully offline.",
  },
  {
    n: "07",
    title: "Connect GitHub — your account, your storage",
    body: "Sign in with GitHub (OAuth on the web, device flow in the CLI) and footprint creates a private footprint-vault repo in your own account. API keys are stored there as hashes, and footprint sync push/pull moves your context between devices through it. footprint has no database and collects nothing — delete the repo and every trace of your account is gone.",
  },
];

const faqs = [
  {
    q: "Does anything leave my machine?",
    a: "No. Transcripts (data/) and trained weights (adapters/) are gitignored and stay local. The model runs on 127.0.0.1 — no upload, no telemetry. The only exception is opt-in: footprint sync push copies them to your own private GitHub repo.",
  },
  {
    q: "What does footprint collect about me?",
    a: "Nothing. There is no footprint database. GitHub sign-in stores a token in an encrypted cookie in your browser; keys and synced context live in a private footprint-vault repo in your GitHub account. Delete that repo and your account no longer exists anywhere.",
  },
  {
    q: "What hardware do I need?",
    a: "Apple Silicon Macs use the MLX backend. Linux and Windows use PyTorch + PEFT with CUDA when available; CPU works but trains slowly. Intel Macs run the CPU torch backend.",
  },
  {
    q: "The output quality feels rough — what helps?",
    a: "More data beats more iterations. Keep tracing, re-collect, and re-train. 1.5B is small; if you have 16 GB+ RAM, try a 7B model via FOOTPRINT_MODEL.",
  },
  {
    q: "How do I point another tool at it?",
    a: "Use base URL http://127.0.0.1:8399/v1 with any API key (or none). In Cursor, add it under Settings → Models; in Codex CLI, define a custom provider in ~/.codex/config.toml.",
  },
];

export default function HowItWorks() {
  return (
    <div className="mx-auto w-full max-w-4xl px-5 py-16 sm:py-24">
      <Badge variant="secondary" className="font-pixel text-xs">
        the pipeline
      </Badge>
      <h1 className="mt-5 text-4xl font-semibold tracking-tight sm:text-5xl">
        From your sessions to a local model.
      </h1>
      {/* Doto accent line on this page */}
      <p className="font-doto mt-4 max-w-2xl text-lg text-foreground/80">
        no tracer, no upload — footprint reads logs claude already wrote.
      </p>

      <VaultNote className="mt-6" />

      <div className="mt-10">
        <CodeBlock title="the flow">
          <span className="text-guava-flesh">trace</span> → chat with claude →{" "}
          <span className="text-guava-flesh">collect</span> →{" "}
          <span className="text-guava-flesh">train</span> →{" "}
          <span className="text-guava-flesh">install</span> →{" "}
          <span className="text-guava-flesh">/footprint</span>
        </CodeBlock>
      </div>

      <ol className="mt-14 space-y-8">
        {pipeline.map((step) => (
          <li key={step.n} className="flex gap-5">
            <div className="font-pixel shrink-0 text-2xl text-guava-flesh">
              {step.n}
            </div>
            <div className="border-b border-border/60 pb-8">
              <h2 className="text-xl font-semibold">{step.title}</h2>
              <p className="mt-2 text-muted-foreground">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>

      <section className="mt-16">
        <h2 className="text-2xl font-semibold tracking-tight">
          Frequently asked
        </h2>
        <Accordion multiple={false} className="mt-4">
          {faqs.map((f) => (
            <AccordionItem key={f.q} value={f.q}>
              <AccordionTrigger className="text-left text-base">
                {f.q}
              </AccordionTrigger>
              <AccordionContent className="text-muted-foreground">
                {f.a}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </section>
    </div>
  );
}
