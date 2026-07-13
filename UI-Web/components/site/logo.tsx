import Link from "next/link";
import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn(
        "font-pixel inline-flex items-center gap-2 text-xl tracking-tight",
        className,
      )}
    >
      <span
        aria-hidden
        className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground text-sm shadow-sm"
      >
        ▚
      </span>
      <span>footprint</span>
    </Link>
  );
}
