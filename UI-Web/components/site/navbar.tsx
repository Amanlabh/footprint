import Link from "next/link";
import { Logo } from "@/components/site/logo";
import { Octocat } from "@/components/site/octocat";
import { StarButton } from "@/components/site/star-button";

const links = [
  { href: "/how-it-works", label: "How it works" },
  { href: "/docs", label: "Docs" },
  { href: "/account", label: "Account" },
];

export function Navbar() {
  return (
    <header className="sticky top-0 z-50 overflow-hidden border-b border-border/60 bg-background/80 backdrop-blur">
      {/* roaming pixel Octocat — patrols the navbar behind the content */}
      <div className="octocat-roam pointer-events-none absolute bottom-1 left-0" aria-hidden>
        <Octocat className="size-8 opacity-80" />
      </div>
      <div className="relative mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-5">
        <Logo />
        <nav className="hidden items-center gap-7 text-sm text-muted-foreground sm:flex">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="transition-colors hover:text-foreground"
            >
              {l.label}
            </Link>
          ))}
        </nav>
        <StarButton />
      </div>
    </header>
  );
}
