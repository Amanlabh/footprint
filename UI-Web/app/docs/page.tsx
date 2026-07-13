import type { Metadata } from "next";
import { CodeBlock } from "@/components/site/code-block";
import { Badge } from "@/components/ui/badge";

export const metadata: Metadata = {
  title: "Docs — footprint",
  description:
    "Install footprint, trace your sessions, train a local model, and serve it OpenAI-compatible.",
};

const commands = [
  ["footprint", "banner + status"],
  ["footprint trace", "arm tracing (run before starting Claude)"],
  ["footprint collect [dir]", "parse a project's transcripts (unknown dir = all projects)"],
  ["footprint train", "LoRA fine-tune on collected data"],
  ["footprint install", "auto-start server + OpenCode integration"],
  ["footprint serve", "run the server manually (fallback)"],
  ["footprint status", "model, example count, adapter, tracing, server state"],
  ["footprint login", "GitHub device-flow sign in (personal environment)"],
  ["footprint key new [label]", "generate an API key — hash stored in your footprint-vault repo"],
  ["footprint sync push|pull", "sync training data + adapters across devices via your vault"],
];

const env = [
  ["FOOTPRINT_MODEL", "Qwen2.5-Coder-1.5B (MLX 4-bit on mac)", "any chat model of the backend"],
  ["FOOTPRINT_ITERS", "300", "training iterations"],
  ["FOOTPRINT_PORT", "8399", "server port"],
];

export default function Docs() {
  return (
    <div className="mx-auto w-full max-w-4xl px-5 py-16 sm:py-24">
      <Badge variant="secondary" className="font-pixel text-xs">
        getting started
      </Badge>
      <h1 className="mt-5 text-4xl font-semibold tracking-tight sm:text-5xl">
        Up and running in a few commands.
      </h1>
      {/* Doto accent line on this page */}
      <p className="font-doto mt-4 max-w-2xl text-lg text-foreground/80">
        install once. trace. collect. train. keep coding offline.
      </p>

      <div className="mt-14 space-y-14">
        <section id="install">
          <h2 className="text-2xl font-semibold tracking-tight">Install</h2>
          <p className="mt-2 text-muted-foreground">
            Requires Claude Code (used at least once), Python 3.9+, and Node
            18+ if installing via npm. The backend is picked automatically —
            MLX on Apple Silicon, PyTorch elsewhere.
          </p>
          <div className="mt-5 space-y-4">
            <CodeBlock title="npm — macOS / Linux / Windows">
              npm install -g footprint-trace
            </CodeBlock>
            <CodeBlock title="from source">
              <span className="text-muted-foreground">$ </span>git clone
              https://github.com/Amanlabh/footprint.git{"\n"}
              <span className="text-muted-foreground">$ </span>cd footprint
              {"\n"}
              <span className="text-muted-foreground">$ </span>python3
              footprint.py setup
            </CodeBlock>
          </div>
        </section>

        <section id="quickstart">
          <h2 className="text-2xl font-semibold tracking-tight">Quickstart</h2>
          <ol className="mt-4 space-y-6">
            <li>
              <p className="font-medium">
                1. Arm tracing — before you start Claude.
              </p>
              <p className="mb-3 mt-1 text-sm text-muted-foreground">
                Trains only on sessions from this point on. Skip it to use your
                whole history.
              </p>
              <CodeBlock>footprint trace</CodeBlock>
            </li>
            <li>
              <p className="font-medium">2. Use Claude Code normally.</p>
              <p className="mb-3 mt-1 text-sm text-muted-foreground">
                Every session is captured automatically.
              </p>
              <CodeBlock>claude</CodeBlock>
            </li>
            <li>
              <p className="font-medium">3. Collect and train.</p>
              <p className="mb-3 mt-1 text-sm text-muted-foreground">
                Transcripts become training data, then a LoRA fine-tune (~10
                min; downloads ~1 GB base model the first time).
              </p>
              <CodeBlock>
                <span className="text-muted-foreground">$ </span>footprint
                collect{"\n"}
                <span className="text-muted-foreground">$ </span>footprint train
              </CodeBlock>
            </li>
            <li>
              <p className="font-medium">4. Install the always-on server.</p>
              <p className="mb-3 mt-1 text-sm text-muted-foreground">
                Registers with launchd / systemd / Task Scheduler and wires up
                OpenCode with a /footprint command.
              </p>
              <CodeBlock>footprint install</CodeBlock>
            </li>
            <li>
              <p className="font-medium">5. Quota over? Keep going.</p>
              <p className="mb-3 mt-1 text-sm text-muted-foreground">
                In OpenCode, or any OpenAI-compatible tool pointed at{" "}
                <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                  http://127.0.0.1:8399/v1
                </code>
                .
              </p>
              <CodeBlock title="OpenCode">
                /footprint fix the failing test in auth.py
              </CodeBlock>
            </li>
          </ol>
        </section>

        <section id="commands">
          <h2 className="text-2xl font-semibold tracking-tight">Commands</h2>
          <div className="mt-4 overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-left text-sm">
              <tbody>
                {commands.map(([cmd, desc]) => (
                  <tr key={cmd} className="border-b border-border/60 last:border-0">
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-guava-flesh">
                      {cmd}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section id="config">
          <h2 className="text-2xl font-semibold tracking-tight">
            Configuration
          </h2>
          <div className="mt-4 overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border/60 bg-secondary/40 font-pixel">
                  <th className="px-4 py-3 font-normal">Env var</th>
                  <th className="px-4 py-3 font-normal">Default</th>
                  <th className="px-4 py-3 font-normal">Notes</th>
                </tr>
              </thead>
              <tbody>
                {env.map(([name, def, note]) => (
                  <tr key={name} className="border-b border-border/60 last:border-0">
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-guava-flesh">
                      {name}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                      {def}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section id="personal-environment">
          <h2 className="text-2xl font-semibold tracking-tight">
            Personal environment
          </h2>
          <p className="mt-2 text-muted-foreground">
            One trained model, one set of API keys, every device — without
            footprint ever holding your data.
          </p>

          <h3 className="mt-8 text-lg font-semibold">
            What the API key is
          </h3>
          <p className="mt-2 text-muted-foreground">
            A footprint API key (
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">fp_…</code>
            ) is your personal-environment credential. Generate it once — on
            the{" "}
            <a href="/account" className="underline underline-offset-2 hover:text-foreground">
              account page
            </a>{" "}
            or with{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
              footprint key new
            </code>{" "}
            — and use the same key on every machine. It identifies your
            environment, so any device carrying it pulls the same context:
            your training data, your trained adapter, your setup. The
            plaintext key is shown exactly once; only its SHA-256 hash is
            stored. Lose it, revoke it, make a new one.
          </p>

          <h3 className="mt-8 text-lg font-semibold">
            How connecting with GitHub works
          </h3>
          <p className="mt-2 text-muted-foreground">
            &ldquo;Continue with GitHub&rdquo; runs the standard OAuth flow
            (the CLI uses GitHub&rsquo;s device flow — type a code, no secret
            on your machine). On first sign-in footprint creates a{" "}
            <span className="font-medium text-foreground">private</span>{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
              footprint-vault
            </code>{" "}
            repo in <em>your</em> GitHub account. Your GitHub identity is your
            footprint account — there is no separate signup, password, or
            profile stored anywhere.
          </p>

          <h3 className="mt-8 text-lg font-semibold">
            No database — your repo is the database
          </h3>
          <p className="mt-2 text-muted-foreground">
            footprint runs no server-side storage at all. Everything an
            account needs lives as files in your private vault repo:{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
              keys.json
            </code>{" "}
            holds the hashed API keys, and{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">data/</code>{" "}
            +{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
              adapters/
            </code>{" "}
            hold your synced context after{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
              footprint sync push
            </code>
            . Git history is the audit log. Delete the repo and your account
            is gone — nothing remains with us, because nothing was ever with
            us. On the website your GitHub token lives only in an encrypted
            cookie in your browser.
          </p>

          <h3 className="mt-8 text-lg font-semibold">
            Same environment on a new device
          </h3>
          <CodeBlock className="mt-3" title="new machine">
            <span className="text-muted-foreground">$ </span>footprint login
            {"\n"}
            <span className="text-muted-foreground">$ </span>footprint sync
            pull{"\n"}
            <span className="text-muted-foreground">
              # same keys, same data, same trained model
            </span>
          </CodeBlock>
        </section>

        <section id="privacy">
          <h2 className="text-2xl font-semibold tracking-tight">Privacy</h2>
          <p className="mt-2 text-muted-foreground">
            Everything stays on your machine. Your transcripts (data/) and the
            weights trained on them (adapters/) are gitignored — never committed,
            never published. MIT licensed.
          </p>
        </section>
      </div>
    </div>
  );
}
