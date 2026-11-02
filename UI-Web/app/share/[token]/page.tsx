import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { BenchReport } from "@/components/site/bench-report";
import { best, label, parity } from "@/lib/bench";
import { readShare } from "@/lib/share";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<Metadata> {
  const s = readShare((await params).token);
  const top = s && best(s);
  return {
    title: s ? `@${s.login} — Claude parity — footprint` : "footprint",
    description: top
      ? `${label(top)} reaches ${parity(top)}% of Claude on @${s.login}'s own work.`
      : undefined,
  };
}

/** Public, opt-in: the summary is sealed in the link itself. Only numbers, no prompts or code. */
export default async function SharePage({ params }: { params: Promise<{ token: string }> }) {
  const s = readShare((await params).token);
  if (!s) notFound();
  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-16 sm:py-20">
      <Badge variant="secondary" className="font-pixel text-xs">
        @{s.login}
      </Badge>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">Claude parity</h1>
      <p className="font-doto mt-2 text-foreground/80">
        free models, measured on real work — not a public benchmark.
      </p>
      <div className="mt-10">
        <BenchReport run={s} />
      </div>
      <p className="mt-10 text-sm text-muted-foreground">
        Measured with <code className="rounded bg-muted px-1.5 py-0.5 text-xs">footprint bench</code>:
        each model replays tasks Claude finished in this developer&apos;s own repos and must pass
        the same check. <a className="underline underline-offset-2 hover:text-foreground" href="/account">Run yours</a>.
      </p>
    </div>
  );
}
