import type { Metadata } from "next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GithubMark } from "@/components/site/github-mark";
import { getSession } from "@/lib/session";
import { listKeys, readBench, VAULT_REPO, type ApiKey } from "@/lib/vault";
import { best, label, parity, type BenchRun } from "@/lib/bench";
import { BenchReport } from "@/components/site/bench-report";
import { CodeBlock } from "@/components/site/code-block";
import { ShareButton } from "./share-button";
import { KeysPanel } from "./keys-panel";
import { SetupSteps } from "./setup-steps";

export const metadata: Metadata = {
  title: "Account — footprint",
  description:
    "Sign in with GitHub and manage the API keys of your footprint personal environment.",
};

export const dynamic = "force-dynamic";

export default async function Account() {
  const session = await getSession();

  if (!session) {
    return (
      <div className="mx-auto w-full max-w-2xl px-5 py-24 text-center">
        <Badge variant="secondary" className="font-pixel text-xs">
          personal environment
        </Badge>
        <h1 className="mt-5 text-4xl font-semibold tracking-tight">
          One environment, every device.
        </h1>
        <p className="font-doto mt-4 text-lg text-foreground/80">
          your keys live in a private repo on your github — not with us.
        </p>
        <p className="mx-auto mt-4 max-w-md text-muted-foreground">
          Signing in creates a private <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{VAULT_REPO}</code>{" "}
          repo in your account. API keys (hashed) and synced context live
          there. We have no database — GitHub is yours.
        </p>
        <div className="mt-8">
          <Button size="lg" render={<a href="/api/auth/login" />}>
            <GithubMark className="size-4" />
            Continue with GitHub
          </Button>
        </div>
      </div>
    );
  }

  let keys: ApiKey[] = [];
  let loadError: string | null = null;
  try {
    keys = await listKeys(session.token, session.login);
  } catch (e) {
    loadError = e instanceof Error ? e.message : "Could not load keys.";
  }
  let runs: BenchRun[] = [];
  try {
    runs = await readBench(session.token, session.login);
  } catch {
    // bench.json unreadable: show the empty state rather than break the page
  }
  const latest = runs[runs.length - 1];

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-16 sm:py-20">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Badge variant="secondary" className="font-pixel text-xs">
            @{session.login}
          </Badge>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">
            API keys
          </h1>
          <p className="font-doto mt-2 text-foreground/80">
            same key, same context, any device.
          </p>
        </div>
        <form action="/api/auth/logout" method="post">
          <Button variant="outline" size="sm" type="submit">
            Sign out
          </Button>
        </form>
      </div>

      <p className="mt-4 text-sm text-muted-foreground">
        Keys are hashed and stored in{" "}
        <a
          className="underline underline-offset-2 hover:text-foreground"
          href={`https://github.com/${session.login}/${VAULT_REPO}`}
          target="_blank"
          rel="noreferrer"
        >
          {session.login}/{VAULT_REPO}
        </a>{" "}
        on your GitHub. Use the same key on another device with{" "}
        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
          footprint login fp_…
        </code>.
      </p>

      <div className="mt-10">
        {loadError ? (
          <p className="text-sm text-destructive">{loadError}</p>
        ) : (
          <KeysPanel keys={keys} />
        )}
      </div>

      <section className="mt-16 border-t border-border/60 pt-12">
        <h2 className="text-2xl font-semibold tracking-tight">Claude parity</h2>
        <p className="font-doto mt-2 text-foreground/80">
          how close free models get to claude — on your own work.
        </p>
        <div className="mt-8">
          {latest ? (
            <div className="space-y-8">
              <BenchReport run={latest} />
              <ShareButton />
              {runs.length > 1 && (
                <div>
                  <h3 className="text-lg font-semibold tracking-tight">History</h3>
                  <ul className="mt-3 space-y-1 text-sm">
                    {[...runs].reverse().slice(0, 10).map((r) => {
                      const b = best(r);
                      return (
                        <li key={r.date} className="flex justify-between gap-4 border-b border-border/60 py-2 last:border-0">
                          <span className="text-muted-foreground">{new Date(r.date).toLocaleDateString()} · {r.tasks} tasks</span>
                          <span>{b ? <><code className="text-xs">{label(b)}</code> · {parity(b)}%</> : "—"}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                No results yet. Replays tasks Claude finished in your repos with any model, then
                uploads <span className="font-medium text-foreground">scores only</span> — never prompts or code.
              </p>
              <CodeBlock>
                <span className="text-muted-foreground">$ </span>footprint bench harvest{"\n"}
                <span className="text-muted-foreground">$ </span>footprint bench run opencode/big-pickle --memory=both{"\n"}
                <span className="text-muted-foreground">$ </span>footprint bench upload
              </CodeBlock>
            </div>
          )}
        </div>
      </section>

      <SetupSteps />
    </div>
  );
}
