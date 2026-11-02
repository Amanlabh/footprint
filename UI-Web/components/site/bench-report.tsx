import { best, label, parity, type BenchRun } from "@/lib/bench";

function Bar({ pct, muted }: { pct: number; muted?: boolean }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-secondary" aria-hidden>
      <div
        className={muted ? "h-full bg-muted-foreground/40" : "h-full bg-guava-flesh"}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/** Claude-parity table for one bench run. Used by /account and the public /share page. */
export function BenchReport({ run }: { run: BenchRun }) {
  const rows = [...run.rows].sort((a, b) => b.passed - a.passed || a.seconds - b.seconds);
  const top = best(run);
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {run.tasks} held-out tasks from your own Claude sessions ·{" "}
        {new Date(run.date).toLocaleDateString()}
      </p>
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[520px] text-left text-sm">
          <thead>
            <tr className="border-b border-border/60 bg-secondary/40 font-pixel">
              <th className="px-4 py-3 font-normal">Model</th>
              <th className="w-1/3 px-4 py-3 font-normal">Claude parity</th>
              <th className="px-4 py-3 font-normal">Pass</th>
              <th className="px-4 py-3 font-normal">Same files</th>
              <th className="px-4 py-3 font-normal">Avg time</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-border/60 text-muted-foreground">
              <td className="px-4 py-3">Claude (reference)</td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                  <Bar pct={100} muted />
                  <span className="w-10 text-right">100%</span>
                </div>
              </td>
              <td className="px-4 py-3">
                {run.tasks}/{run.tasks}
              </td>
              <td className="px-4 py-3">100%</td>
              <td className="px-4 py-3">—</td>
            </tr>
            {rows.map((r) => (
              <tr key={label(r)} className="border-b border-border/60 last:border-0">
                <td className="px-4 py-3 font-mono text-xs">{label(r)}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <Bar pct={parity(r)} />
                    <span className="w-10 text-right font-medium">{parity(r)}%</span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  {r.passed}/{r.total}
                </td>
                <td className="px-4 py-3">{Math.round(r.overlap * 100)}%</td>
                <td className="px-4 py-3">{r.seconds}s</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {top && (
        <p className="text-sm">
          <span className="font-medium">Best free option for this work:</span>{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">{label(top)}</code> — use it
          when Claude runs out.
        </p>
      )}
      {run.tasks < 10 && (
        <p className="text-xs text-muted-foreground">
          Only {run.tasks} task{run.tasks === 1 ? "" : "s"} — treat as a rough signal. More
          Claude sessions that run a check and end in a commit make it sharper.
        </p>
      )}
    </div>
  );
}
