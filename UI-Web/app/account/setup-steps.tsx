import { CodeBlock } from "@/components/site/code-block";

const INSTALL = "curl -fsSL https://www.tracefootprint.space/install.sh | sh -s -- fp_yourkey";

const $ = <span className="text-muted-foreground">$ </span>;

// Local model pipeline, in order: what each command does and why it's needed (from service.py / backends).
const localModelSteps: { cmd: string; what: string; why: string }[] = [
  {
    cmd: "footprint setup",
    what: "Creates a private Python environment in ~/.footprint/app/.venv and installs the training engine: MLX on a Mac, PyTorch + transformers on Linux/Windows (~2 GB). One time only.",
    why: "Training libraries are large; keeping them in their own environment means they never touch your system Python. train / eval / serve / install run it for you if you skip it.",
  },
  {
    cmd: "footprint trace",
    what: "Marks \"now\": only Claude sessions from this moment on become training data.",
    why: "Lets you choose what the model learns from — skip old or unrelated history. Skip this command to train on all your past sessions.",
  },
  {
    cmd: "…work with Claude Code for a while",
    what: "Use Claude normally on real tasks.",
    why: "These sessions are the lessons. More sessions = more examples = a better model.",
  },
  {
    cmd: "footprint collect",
    what: "Turns your Claude sessions (this project, or all projects) into training examples: \"conversation so far → what Claude did next\". Keeps 10% aside for testing.",
    why: "A model can't learn from raw transcripts; it needs example pairs. The 10% held back is what eval tests on.",
  },
  {
    cmd: "footprint train",
    what: "LoRA fine-tune: trains a small add-on (~20 MB adapter) on top of the base model (Qwen2.5-Coder 1.5B). Minutes to hours; the laptop gets hot.",
    why: "Teaches the model your and Claude's working style without changing or re-downloading the base model.",
  },
  {
    cmd: "footprint eval",
    what: "Scores the trained model on the 10% it never saw (loss + perplexity — lower is better).",
    why: "Confirms it actually learned before you rely on it. It measures text prediction, not task success — use footprint bench for that.",
  },
  {
    cmd: "footprint install",
    what: "Registers a background service (launchd / systemd / Task Scheduler) that runs the model at localhost:8399 on login and restarts it if it crashes. Adds a \"footprint\" model and a /footprint command to OpenCode.",
    why: "So you never start it by hand — in OpenCode just pick the footprint model with /models.",
  },
  {
    cmd: "footprint serve",
    what: "Runs the same model server in the foreground, in this terminal.",
    why: "Only for debugging, or if you don't want a background service. Not needed after install.",
  },
  {
    cmd: "footprint status",
    what: "Shows the engine (mlx / torch), the base model, how many training examples you have, and whether a trained adapter exists.",
    why: "A quick check of where you are in these steps.",
  },
];

// First-time path: everything a new user needs, in order. Nothing optional here.
const steps: { title: string; body: React.ReactNode; code?: React.ReactNode; slot?: "keys" }[] = [
  {
    title: "Check you have Python 3",
    body: "That's all footprint needs — no npm, no git. macOS or Linux (Windows coming). No Python on a Mac? Run xcode-select --install.",
    code: <>{$}python3 --version</>,
  },
  {
    title: "Generate your key",
    body: "Type a label (e.g. macbook) and click Generate API key. The key is shown once, inside a ready-to-paste install command — copy that command.",
    slot: "keys",
  },
  {
    title: "Install and sign in",
    body: "Paste the copied command in your terminal. It installs footprint, signs you in, and connects it to Claude Code and OpenCode.",
    code: <>{$}{INSTALL}</>,
  },
  {
    title: "Open a new terminal and check it works",
    body: "Prints your last session in this folder — or \"no previous session\", which is normal on day one.",
    code: <>{$}footprint context</>,
  },
  {
    title: "Get OpenCode — your free fallback",
    body: "A free coding agent with free models. Skip if you already have it.",
    code: <>{$}curl -fsSL https://opencode.ai/install | bash</>,
  },
  {
    title: "Work in Claude Code as usual",
    body: "Nothing changes. footprint quietly remembers each session: the goal, files, todos, last error, and how tasks were solved.",
    code: (
      <>
        {$}cd my-project{"\n"}
        {$}claude
      </>
    ),
  },
  {
    title: "Claude ran out? Open OpenCode in the same project",
    body: "It already knows where you stopped, and each prompt gets your similar past work. Pick a free model with /models (Big Pickle). A chat already open? Type /continue.",
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
      ["footprint setup", "one-time: install the local model backend (train/serve/install run it for you)"],
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

const h2 = "text-2xl font-semibold tracking-tight";
const section = "mt-16 border-t border-border/60 pt-12";

export function GetStarted({ keys }: { keys: React.ReactNode }) {
  return (
    <section className="mt-12">
      <h2 className={h2}>Get started</h2>
      <p className="font-doto mt-2 text-foreground/80">seven steps, about two minutes. do them in order.</p>
      <ol className="mt-8 space-y-10">
        {steps.map((s, i) => (
          <li key={s.title}>
            <p className="font-medium">
              {i + 1}. {s.title}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{s.body}</p>
            {s.code && <CodeBlock className="mt-3">{s.code}</CodeBlock>}
            {s.slot === "keys" && <div className="mt-4">{keys}</div>}
          </li>
        ))}
      </ol>
      <p className="mt-10 rounded-xl border border-guava-rind/60 bg-accent/40 p-4 text-sm">
        <span className="font-medium">That&apos;s it.</span> From now on, whenever Claude runs out, open
        OpenCode in the same folder and keep going.
      </p>
    </section>
  );
}

function Extra({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border p-5">
      <h3 className="font-medium">{title}</h3>
      <div className="mt-2 space-y-3 text-sm text-muted-foreground">{children}</div>
    </div>
  );
}

/** Optional extras, once the basics work. `parity` = the user's bench results (if any). */
export function GoFurther({ parity }: { parity: React.ReactNode }) {
  return (
    <section className={section}>
      <h2 className={h2}>Go further</h2>
      <p className="font-doto mt-2 text-foreground/80">optional — once the basics work.</p>
      <div className="mt-8 space-y-6">
        <Extra title="Continue the exact same chat">
          <p>Moves your whole Claude Code conversation into OpenCode, message by message.</p>
          <CodeBlock>{$}footprint switch</CodeBlock>
        </Extra>

        <Extra title="Find the free model that works best for you">
          <p>
            Replays tasks Claude finished in your repos with any model and scores them (Claude parity).
            Only the scores are uploaded — never prompts or code.
          </p>
          <CodeBlock>
            {$}footprint bench harvest{"\n"}
            {$}footprint bench run opencode/big-pickle --memory=both{"\n"}
            {$}footprint bench upload
          </CodeBlock>
          {parity}
        </Extra>

        <Extra title="Train a local model (advanced)">
          <p>
            An offline model that learns from your Claude sessions. Needs an Apple Silicon Mac with 16GB+
            (or an NVIDIA GPU) and gets hot while training. The base model is small (1.5B): it picks up
            your style but is weak at agent tasks — check it with footprint bench.
          </p>
          <details className="group">
            <summary className="cursor-pointer font-medium text-foreground">
              Show the steps (what each does and why)
            </summary>
            <ol className="mt-4 space-y-4 border-l border-border pl-4">
              {localModelSteps.map((d, j) => (
                <li key={d.cmd}>
                  <p>
                    <span>{String.fromCharCode(97 + j)}. </span>
                    <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-guava-flesh">{d.cmd}</code>
                  </p>
                  <p className="mt-1">
                    <span className="font-medium text-foreground">What: </span>
                    {d.what}
                  </p>
                  <p className="mt-0.5">
                    <span className="font-medium text-foreground">Why: </span>
                    {d.why}
                  </p>
                </li>
              ))}
            </ol>
          </details>
        </Extra>
      </div>
    </section>
  );
}

export function CommandReference() {
  return (
    <section className={section}>
      <details>
        <summary className={`${h2} cursor-pointer`}>All commands</summary>
        <div className="mt-6 space-y-8">
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
      </details>
    </section>
  );
}

const faq: [string, string][] = [
  ["“footprint: command not found”", "Open a new terminal (step 4)."],
  ["“key rejected”", "The key was revoked, mistyped, or made before 2 Nov 2026. Generate a new one in step 2, then run footprint login fp_…"],
  ["No handover in a new session", "Run footprint context in that folder. “No previous session” means nothing recent happened there yet."],
  ["Another device", "Run the same install command there — same key or a new one."],
  ["Update footprint", "Re-run the install command. Your data is kept."],
  ["Lost a key", "Revoke it in step 2 — every machine using it stops. Then generate a new one."],
];

export function Troubleshooting() {
  return (
    <section className={section}>
      <h2 className={h2}>Troubleshooting</h2>
      <dl className="mt-6 space-y-4 text-sm">
        {faq.map(([q, a]) => (
          <div key={q}>
            <dt className="font-medium">{q}</dt>
            <dd className="mt-0.5 text-muted-foreground">{a}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
