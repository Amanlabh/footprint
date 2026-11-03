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

// First-time user path, in order. Required steps first; optional ones are marked.
const steps: {
  title: string;
  body: React.ReactNode;
  code?: React.ReactNode;
  optional?: boolean;
  detail?: { cmd: string; what: string; why: string }[];
}[] = [
  {
    title: "Check you have Python 3",
    body: "footprint needs nothing else — no npm, no git. macOS / Linux for now (Windows coming). If this prints a version, you're set; on macOS without it, run xcode-select --install.",
    code: <>{$}python3 --version</>,
  },
  {
    title: "Generate your key",
    body: "Above: type a label (e.g. macbook) → Generate API key. It is shown once, with the install command already filled in. Copy that command.",
  },
  {
    title: "Install + sign in",
    body: "Paste the copied command in your terminal. It installs footprint, signs you in, and hooks into Claude Code and OpenCode.",
    code: <>{$}{INSTALL}</>,
  },
  {
    title: "Open a new terminal and check it works",
    body: "A new terminal picks up the footprint command. This prints your last session in this folder — or \"no previous session\", which is fine on day one.",
    code: <>{$}footprint context</>,
  },
  {
    title: "Get OpenCode (your free fallback)",
    body: "Free coding agent with free models (Big Pickle). Skip if you already have it.",
    code: <>{$}curl -fsSL https://opencode.ai/install | bash</>,
  },
  {
    title: "Work in Claude Code as usual",
    body: "Nothing to change. footprint quietly remembers each session: goal, files, todos, last error, how tasks were solved.",
    code: (
      <>
        {$}cd my-project{"\n"}
        {$}claude
      </>
    ),
  },
  {
    title: "Claude ran out? Open OpenCode in the same project",
    body: "The new session already knows where you stopped, and every prompt gets your similar past work — any model. Pick a model with /models (Big Pickle is free). Chat already open? Type /continue.",
    code: (
      <>
        {$}cd my-project{"\n"}
        {$}opencode
      </>
    ),
  },
  {
    title: "Want the exact same chat instead?",
    body: "Moves your whole Claude Code conversation into OpenCode, message by message.",
    code: <>{$}footprint switch</>,
    optional: true,
  },
  {
    title: "Measure which free model works best for you",
    body: "Replays tasks Claude finished in your repos with any model and scores them. Scores (numbers only) appear in Claude parity above; share them with a public link + badge if you like.",
    code: (
      <>
        {$}footprint bench harvest{"\n"}
        {$}footprint bench run opencode/big-pickle --memory=both{"\n"}
        {$}footprint bench upload
      </>
    ),
    optional: true,
  },
  {
    title: "Train a local model on your sessions",
    body: "Advanced: an offline model that learned from your Claude sessions. Needs an Apple Silicon Mac with 16GB+ (or an NVIDIA GPU), and makes it hot while training. Honest note: the base model is small (1.5B) — it picks up style, but is weak at agent tasks; check it with footprint bench. Run these in order:",
    detail: localModelSteps,
    optional: true,
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

export function SetupSteps() {
  return (
    <section className="mt-16 border-t border-border/60 pt-12">
      <h2 className="text-2xl font-semibold tracking-tight">Get started</h2>
      <p className="font-doto mt-2 text-foreground/80">first time? follow these in order — steps 1–7 take two minutes.</p>

      <ol className="mt-8 space-y-8">
        {steps.map((s, i) => (
          <li key={s.title}>
            <p className="font-medium">
              {i + 1}. {s.title}
              {s.optional && (
                <span className="ml-2 rounded-full bg-secondary px-2 py-0.5 align-middle font-pixel text-[10px] text-muted-foreground">
                  optional
                </span>
              )}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">{s.body}</p>
            {s.code && <CodeBlock className="mt-3">{s.code}</CodeBlock>}
            {s.detail && (
              <ol className="mt-4 space-y-4 border-l border-border pl-4">
                {s.detail.map((d, j) => (
                  <li key={d.cmd} className="text-sm">
                    <p>
                      <span className="text-muted-foreground">{String.fromCharCode(97 + j)}. </span>
                      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-guava-flesh">{d.cmd}</code>
                    </p>
                    <p className="mt-1 text-muted-foreground">
                      <span className="font-medium text-foreground">What: </span>
                      {d.what}
                    </p>
                    <p className="mt-0.5 text-muted-foreground">
                      <span className="font-medium text-foreground">Why: </span>
                      {d.why}
                    </p>
                  </li>
                ))}
              </ol>
            )}
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
          <span className="font-medium text-foreground">“footprint: command not found”?</span> Open a
          new terminal (step 4).
        </li>
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
