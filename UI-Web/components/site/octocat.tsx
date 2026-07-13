import { cn } from "@/lib/utils";

const PX = 6;

// Pixel Octocat: '#' = body, 'o' = eye (cut-out)
const BODY = [
  "..#......#..",
  "..##....##..",
  "..########..",
  ".##########.",
  ".#o######o#.",
  ".##########.",
  "..########..",
  "..########..",
  "..########..",
];

// Two tentacle frames — alternating gives the walk cycle
const LEGS_A = ["..#..##..#..", "..#..##..#..", ".#........#."];
const LEGS_B = [".#...##...#.", ".#...##...#.", "..#......#.."];

function rects(lines: string[], rowOffset = 0) {
  const out: React.ReactNode[] = [];
  lines.forEach((line, r) => {
    [...line].forEach((ch, c) => {
      if (ch === "#" || ch === "o") {
        out.push(
          <rect
            key={`${r}-${c}`}
            x={c * PX}
            y={(r + rowOffset) * PX}
            width={PX}
            height={PX}
            fill={ch === "o" ? "var(--card)" : "currentColor"}
          />,
        );
      }
    });
  });
  return out;
}

export function Octocat({ className }: { className?: string }) {
  return (
    <span
      aria-label="animated pixel Octocat"
      role="img"
      className={cn("octocat-hop inline-block text-primary", className)}
    >
      <svg
        viewBox={`0 0 ${12 * PX} ${12 * PX}`}
        width="100%"
        height="100%"
        shapeRendering="crispEdges"
      >
        {rects(BODY)}
        <g className="octocat-legs-a">{rects(LEGS_A, 9)}</g>
        <g className="octocat-legs-b">{rects(LEGS_B, 9)}</g>
      </svg>
    </span>
  );
}
