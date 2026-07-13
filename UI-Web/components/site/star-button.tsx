import { Star } from "lucide-react";
import { GithubMark } from "@/components/site/github-mark";

const REPO = "Amanlabh/footprint";

async function getStars(): Promise<number | null> {
  try {
    const res = await fetch(`https://api.github.com/repos/${REPO}`, {
      headers: { Accept: "application/vnd.github+json" },
      next: { revalidate: 3600 }, // refresh count hourly
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { stargazers_count?: number };
    return typeof data.stargazers_count === "number"
      ? data.stargazers_count
      : null;
  } catch {
    return null;
  }
}

function fmt(n: number) {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

export async function StarButton() {
  const stars = await getStars();
  return (
    <a
      href={`https://github.com/${REPO}`}
      target="_blank"
      rel="noreferrer"
      className="group inline-flex items-center overflow-hidden rounded-lg border border-border bg-background text-sm font-medium shadow-sm transition-colors hover:bg-muted"
    >
      <span className="flex items-center gap-1.5 px-2.5 py-1.5">
        <GithubMark className="size-4" />
        <Star className="size-3.5 text-guava-flesh transition-transform group-hover:scale-110 group-hover:fill-guava-flesh" />
        <span>Star</span>
      </span>
      {stars !== null && (
        <span className="border-l border-border bg-secondary/60 px-2.5 py-1.5 font-pixel text-xs tabular-nums">
          {fmt(stars)}
        </span>
      )}
    </a>
  );
}
