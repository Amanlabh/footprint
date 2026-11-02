"use client";

import { useActionState } from "react";
import { Copy, Share2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { shareBenchAction } from "./actions";

function CopyRow({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="mt-1 flex items-center gap-2">
        <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-lg bg-card px-3 py-2 font-mono text-xs">
          {text}
        </code>
        <Button variant="outline" size="icon" type="button" aria-label={`Copy ${label}`}
          onClick={() => navigator.clipboard.writeText(text)}>
          <Copy className="size-4" />
        </Button>
      </div>
    </div>
  );
}

/** Nothing is public until this is clicked. */
export function ShareButton() {
  const [state, action, pending] = useActionState(shareBenchAction, { path: null, error: null });
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const url = state.path ? origin + state.path : null;
  return (
    <div className="space-y-3">
      <form action={action}>
        <Button variant="outline" size="sm" type="submit" disabled={pending}>
          <Share2 className="size-4" />
          {pending ? "Creating…" : "Create public share link + badge"}
        </Button>
      </form>
      {state.error && <p className="text-sm text-destructive">{state.error}</p>}
      {url && (
        <div className="space-y-3 rounded-xl border border-border p-4">
          <p className="text-xs text-muted-foreground">
            Anyone with this link sees the scores above (numbers only — no prompts or code).
          </p>
          <CopyRow label="Share link" text={url} />
          <CopyRow
            label="README badge (markdown)"
            text={`[![footprint](${origin}${state.path!.replace("/share/", "/api/badge/")})](${url})`}
          />
        </div>
      )}
    </div>
  );
}
