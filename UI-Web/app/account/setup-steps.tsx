import { CodeBlock } from "@/components/site/code-block";

const INSTALL = "curl -fsSL https://www.tracefootprint.space/install.sh | sh -s -- fp_yourkey";

const $ = <span className="text-muted-foreground">$ </span>;

const steps: { title: string; body: React.ReactNode; code?: React.ReactNode }[] = [
  {
    title: "Generate your key",
    body: "Type a label (e.g. macbook) and click Generate API key above. The key is shown once, with the install command already filled in. Copy it.",
  },
  {
    title: "Install + sign in",
    body: "Paste it in your terminal. Needs Python 3 (macOS: run xcode-select --install if missing). No npm, no git.",
    code: <>{$}{INSTALL}</>,
  },
  {
    title: "Open a new terminal",
    body: "So the footprint command is on your PATH. Check it:",
    code: <>{$}footprint status</>,
  },
  {
    title: "Get a coding tool (if you don't have one)",
    body: "OpenCode is free. Claude Code works too.",
    code: <>{$}curl -fsSL https://opencode.ai/install | bash</>,
  },
  {
    title: "Work in any project",
    body: "Your next session in the same project starts where the last one left off — goal, files, todos, last error. Switch between Claude Code and OpenCode freely.",
    code: (
      <>
        {$}cd my-project{"\n"}
        {$}opencode
      </>
    ),
  },
];

// Mirrors footprint_core/cli.py. key/sync are left out on purpose: they still need the old GitHub
// device sign-in (see gaps.md) — keys are managed above, on this page.
const commandGroups: { title: string; note?: string; rows: [string, string][] }[] = [
  {
    title: "Inside your coding tool",
    rows: [
      ["/continue [next task]", "OpenCode: pull the last session's state into a chat that was already open"],
      ["/clear", "Claude Code: fresh chat that still starts with the last session's state"],
    ],
  },
  {
    title: "Account & updates",
    rows: [
      ["footprint login fp_…", "sign in on this device with a key from this page"],
      ["curl -fsSL https://www.tracefootprint.space/install.sh | sh", "re-run to update footprint (your data is kept)"],
    ],
  },
  {
    title: "Continuity & memory",
    rows: [
      ["footprint context", "preview what the next session will be handed"],
      ["footprint context install", "(re)install the Claude Code hooks + OpenCode plugin"],
      ["footprint recall <text>", "similar past work footprint adds to a prompt like that"],
      ["footprint switch", "open your latest Claude Code chat in OpenCode, full history"],
      ["footprint switch list", "list recent Claude Code sessions with their ids"],
      ["footprint switch <session-id>", "open that specific Claude Code chat in OpenCode"],
    ],
  },
  {
    title: "Claude parity bench",
    rows: [
      ["footprint bench harvest [n]", "pick up to n (default 20) tasks Claude finished in your repos as the answer key"],
      ["footprint bench run <provider/model>… --memory=both", "replay them with any model, with and without memory (on | off | both)"],
      ["footprint bench", "show the latest report in the terminal"],
      ["footprint bench upload", "send the scores (numbers only) to this page"],
    ],
  },
  {
    title: "Local model (optional)",
    note: "Trains a small model on your own laptop — needs an Apple Silicon Mac (16GB+) or an NVIDIA GPU, and makes it hot.",
    rows: [
      ["footprint trace", "only sessions from now on become training data (run before chatting)"],
      ["footprint collect [project]", "turn your Claude sessions into training data"],
      ["footprint train", "LoRA fine-tune the local model on that data"],
      ["footprint eval", "test loss + perplexity on held-out data"],
      ["footprint install", "keep the local model running and add it to OpenCode as \"footprint\""],
      ["footprint serve", "run the local model API at localhost:8399 by hand"],
      ["footprint status", "local model state: backend, model, training examples"],
    ],
  },
];

export function SetupSteps() {
  return (
    <section className="mt-16 border-t border-border/60 pt-12">
      <h2 className="text-2xl font-semibold tracking-tight">Get started</h2>
      <p className="font-doto mt-2 text-foreground/80">two minutes, one command.</p>

      <ol className="mt-8 space-y-8">
        {steps.map((s, i) => (
          <li key={s.title}>
            <p className="font-medium">
              {i + 1}. {s.title}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{s.body}</p>
            {s.code && <CodeBlock className="mt-3">{s.code}</CodeBlock>}
          </li>
        ))}
      </ol>

      <h3 className="mt-12 text-lg font-semibold tracking-tight">All commands</h3>
      <div className="mt-4 space-y-8">
        {commandGroups.map((g) => (
          <div key={g.title}>
            <p className="font-pixel text-xs text-muted-foreground">{g.title}</p>
            {g.note && <p className="mt-1 text-xs text-muted-foreground">{g.note}</p>}
            <div className="mt-2 overflow-x-auto rounded-xl border border-border">
              <table className="w-full text-left text-sm">
                <tbody>
                  {g.rows.map(([cmd, what]) => (
                    <tr key={cmd} className="border-b border-border/60 last:border-0">
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-guava-flesh">{cmd}</td>
                      <td className="px-4 py-3 text-muted-foreground">{what}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>

      <ul className="mt-8 space-y-2 text-sm text-muted-foreground">
        <li>
          <span className="font-medium text-foreground">Another device?</span> Run the same
          install command there — same key or a new one.
        </li>
        <li>
          <span className="font-medium text-foreground">Update?</span> Re-run the install
          command. Your data is kept.
        </li>
        <li>
          <span className="font-medium text-foreground">Lost a key?</span> Revoke it above —
          every machine using it stops working. Generate a new one.
        </li>
        <li>
          <span className="font-medium text-foreground">“key rejected”?</span> The key was
          revoked or mistyped, or made before 2 Nov 2026 — generate a new one.
        </li>
      </ul>
    </section>
  );
}
