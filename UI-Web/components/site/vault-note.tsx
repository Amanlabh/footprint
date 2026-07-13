import { GithubMark } from "@/components/site/github-mark";
import { cn } from "@/lib/utils";

export function VaultNote({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex max-w-xl items-start gap-3 rounded-xl border border-guava-rind/50 bg-accent/30 px-4 py-3",
        className,
      )}
    >
      <GithubMark className="mt-0.5 size-4 shrink-0" />
      <p className="text-sm text-muted-foreground">
        <span className="font-medium text-foreground">
          Your GitHub is the account — we collect nothing.
        </span>{" "}
        Signing in creates a private{" "}
        <code className="rounded bg-muted px-1 py-0.5 text-xs">
          footprint-vault
        </code>{" "}
        repo in <em>your</em> account. API keys and synced context live there;
        footprint runs no database and never sees your data.
      </p>
    </div>
  );
}
