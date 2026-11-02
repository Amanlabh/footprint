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

const commands: [string, string][] = [
  ["/continue [next task]", "inside OpenCode: pull in the last session's state into a chat that was already open"],
  ["/clear", "inside Claude Code: fresh chat that still starts with the last session's state"],
  ["footprint context", "preview what the next session will be handed"],
  ["footprint switch", "open your latest Claude Code chat in OpenCode, full history"],
  ["footprint status", "what's installed and signed in"],
  ["footprint login fp_…", "sign in again with a new key"],
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

      <h3 className="mt-12 text-lg font-semibold tracking-tight">Handy commands</h3>
      <div className="mt-4 overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-left text-sm">
          <tbody>
            {commands.map(([cmd, what]) => (
              <tr key={cmd} className="border-b border-border/60 last:border-0">
                <td className="whitespace-nowrap px-4 py-3 font-mono text-guava-flesh">{cmd}</td>
                <td className="px-4 py-3 text-muted-foreground">{what}</td>
              </tr>
            ))}
          </tbody>
        </table>
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
