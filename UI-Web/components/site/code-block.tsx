import { cn } from "@/lib/utils";

export function CodeBlock({
  children,
  title,
  className,
}: {
  children: React.ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-border bg-card shadow-sm",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-b border-border/60 bg-secondary/50 px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-guava-flesh" />
        <span className="size-2.5 rounded-full bg-guava-seed" />
        <span className="size-2.5 rounded-full bg-guava-rind" />
        {title ? (
          <span className="ml-2 font-pixel text-xs text-muted-foreground">
            {title}
          </span>
        ) : null}
      </div>
      <pre className="overflow-x-auto px-4 py-4 font-mono text-sm leading-relaxed">
        {children}
      </pre>
    </div>
  );
}
