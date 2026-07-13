import type { Metadata } from "next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GithubMark } from "@/components/site/github-mark";
import { getSession } from "@/lib/session";
import { listKeys, VAULT_REPO, type ApiKey } from "@/lib/vault";
import { KeysPanel } from "./keys-panel";

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
          footprint login
        </code>{" "}
        + <code className="rounded bg-muted px-1.5 py-0.5 text-xs">footprint sync pull</code>.
      </p>

      <div className="mt-10">
        {loadError ? (
          <p className="text-sm text-destructive">{loadError}</p>
        ) : (
          <KeysPanel keys={keys} />
        )}
      </div>
    </div>
  );
}
