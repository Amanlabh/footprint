import Link from "next/link";
import { Logo } from "@/components/site/logo";

export function Footer() {
  return (
    <footer className="border-t border-border/60 bg-secondary/40">
      <div className="mx-auto w-full max-w-6xl px-5 py-12">
        <div className="flex flex-col gap-8 md:flex-row md:items-start md:justify-between">
          <div className="max-w-sm space-y-3">
            <Logo />
            {/* Doto accent line in the footer */}
            <p className="font-doto text-sm text-muted-foreground">
              your claude, learned locally. offline. private. yours.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-10 text-sm">
            <div className="space-y-2">
              <p className="font-medium">Product</p>
              <Link
                href="/how-it-works"
                className="block text-muted-foreground hover:text-foreground"
              >
                How it works
              </Link>
              <Link
                href="/docs"
                className="block text-muted-foreground hover:text-foreground"
              >
                Docs
              </Link>
            </div>
            <div className="space-y-2">
              <p className="font-medium">Source</p>
              <a
                href="https://github.com/Amanlabh/footprint"
                target="_blank"
                rel="noreferrer"
                className="block text-muted-foreground hover:text-foreground"
              >
                GitHub
              </a>
              <a
                href="https://www.npmjs.com/package/footprint-trace"
                target="_blank"
                rel="noreferrer"
                className="block text-muted-foreground hover:text-foreground"
              >
                npm — footprint-trace
              </a>
            </div>
          </div>
        </div>
        <div className="mt-10 flex flex-col gap-2 border-t border-border/60 pt-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span className="font-pixel text-sm">footprint</span>
          <span>MIT licensed · Everything stays on your machine.</span>
        </div>
      </div>
    </footer>
  );
}
