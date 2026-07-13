import Link from "next/link";
import { cn } from "@/lib/utils";
import { Octocat } from "@/components/site/octocat";

export function Logo({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      className={cn(
        "font-pixel inline-flex items-center gap-2 text-xl tracking-tight",
        className,
      )}
    >
      <Octocat still className="size-6" />
      <span>footprint</span>
    </Link>
  );
}
