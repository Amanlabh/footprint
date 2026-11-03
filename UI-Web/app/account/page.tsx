import type { Metadata } from "next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GithubMark } from "@/components/site/github-mark";
import { getSession } from "@/lib/session";
import { listKeys, readBench, VAULT_REPO, type ApiKey } from "@/lib/vault";
import { best, label, parity, type BenchRun } from "@/lib/bench";
import { BenchReport } from "@/components/site/bench-report";
import { ShareButton } from "./share-button";
import { KeysPanel } from "./keys-panel";
import { CommandReference, GetStarted, GoFurther, Troubleshooting } from "./setup-steps";

export const metadata: Metadata = {
  title: "Account — footprint",
  description:
    "Get your footprint key and a two-minute setup: keep coding on any model when Claude runs out.",
};

export const dynamic = "force-dynamic";

export default async function Account() {
  const session = await getSession();

  if (!session) {
    return (
      <div className="mx-auto w-full max-w-2xl px-5 py-24 text-center">
        <Badge variant="secondary" className="font-pixel text-xs">
          footprint
        </Badge>
        <h1 className="mt-5 text-4xl font-semibold tracking-tight">
          Keep coding when Claude runs out.
        </h1>
        <p className="font-doto mt-4 text-lg text-foreground/80">
          any model picks up exactly where you stopped.
        </p>
        <p className="mx-auto mt-4 max-w-md text-muted-foreground">
          Sign in to get your key and a two-minute setup. Your keys are stored (hashed) in a
          private <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{VAULT_REPO}</code>{" "}
          repo on your own GitHub — we have no database.
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

  const keysSlot = loadError ? (
    <p className="text-sm text-destructive">{loadError}</p>
  ) : (
    <div className="space-y-3">
      <KeysPanel keys={keys} />
      <p className="text-xs text-muted-foreground">
        Stored hashed in your private{" "}
        <a
          className="underline underline-offset-2 hover:text-foreground"
          href={`https://github.com/${session.login}/${VAULT_REPO}`}
          target="_blank"
          rel="noreferrer"
        >
          {session.login}/{VAULT_REPO}
        </a>{" "}
        repo — not on our servers.
      </p>
    </div>
  );

  const paritySlot = latest && (
    <div className="space-y-6 pt-2 text-foreground">
      <BenchReport run={latest} />
      <ShareButton />
      {runs.length > 1 && (
        <div>
          <p className="font-medium">History</p>
          <ul className="mt-2 space-y-1">
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
  );

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-16 sm:py-20">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Badge variant="secondary" className="font-pixel text-xs">
            @{session.login}
          </Badge>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">Your footprint</h1>
          <p className="font-doto mt-2 text-foreground/80">
            keep coding when claude runs out — any model picks up where you stopped.
          </p>
        </div>
        <form action="/api/auth/logout" method="post">
          <Button variant="outline" size="sm" type="submit">
            Sign out
          </Button>
        </form>
      </div>

      <GetStarted keys={keysSlot} />
      <GoFurther parity={paritySlot} />
      <CommandReference />
      <Troubleshooting />
    </div>
  );
}
