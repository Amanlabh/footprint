"use client";

import { useActionState } from "react";
import { KeyRound, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { generateKeyAction, revokeKeyAction } from "./actions";
import type { ApiKey } from "@/lib/vault";

export function KeysPanel({ keys }: { keys: ApiKey[] }) {
  const [state, formAction, pending] = useActionState(generateKeyAction, {
    key: null,
    error: null,
  });

  return (
    <div className="space-y-8">
      <form action={formAction} className="flex flex-wrap items-center gap-3">
        <input
          name="label"
          placeholder="key label (e.g. macbook)"
          className="h-9 rounded-lg border border-border bg-background px-3 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        />
        <Button size="lg" disabled={pending} type="submit">
          <KeyRound className="size-4" />
          {pending ? "Generating…" : "Generate API key"}
        </Button>
      </form>

      {state.error && (
        <p className="text-sm text-destructive">{state.error}</p>
      )}

      {state.key && (
        <div className="rounded-xl border border-guava-rind/60 bg-accent/40 p-4">
          <p className="font-pixel text-xs text-accent-foreground">
            your new key — copy it now, it is never shown again
          </p>
          <div className="mt-2 flex items-center gap-2">
            <code className="overflow-x-auto rounded-lg bg-card px-3 py-2 font-mono text-sm">
              {state.key}
            </code>
            <Button
              variant="outline"
              size="icon"
              type="button"
              aria-label="Copy key"
              onClick={() => navigator.clipboard.writeText(state.key!)}
            >
              <Copy className="size-4" />
            </Button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border/60 bg-secondary/40 font-pixel">
              <th className="px-4 py-3 font-normal">Key</th>
              <th className="px-4 py-3 font-normal">Label</th>
              <th className="px-4 py-3 font-normal">Created</th>
              <th className="px-4 py-3 font-normal" />
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-muted-foreground">
                  No keys yet. Generate one above — it lands in
                  footprint-vault/keys.json on your GitHub.
                </td>
              </tr>
            )}
            {keys.map((k) => (
              <tr key={k.prefix} className="border-b border-border/60 last:border-0">
                <td className="whitespace-nowrap px-4 py-3 font-mono text-guava-flesh">
                  {k.prefix}…
                </td>
                <td className="px-4 py-3">{k.label}</td>
                <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">
                  {new Date(k.created).toLocaleDateString()}
                </td>
                <td className="px-4 py-3 text-right">
                  <form action={revokeKeyAction}>
                    <input type="hidden" name="prefix" value={k.prefix} />
                    <Button variant="destructive" size="sm" type="submit">
                      Revoke
                    </Button>
                  </form>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
