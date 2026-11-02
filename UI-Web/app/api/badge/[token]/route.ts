import { best, parity } from "@/lib/bench";
import { readShare } from "@/lib/share";

/** README badge: "footprint | 85% Claude parity". Only numbers are rendered, so no escaping concerns. */
export async function GET(_req: Request, { params }: { params: Promise<{ token: string }> }) {
  const s = readShare((await params).token);
  const top = s && best(s);
  const right = top ? `${parity(top)}% Claude parity` : "invalid link";
  const lw = 70;
  const rw = 8 + right.length * 7;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${lw + rw}" height="20" role="img" aria-label="footprint: ${right}">
<rect width="${lw}" height="20" fill="#3a2a2e"/><rect x="${lw}" width="${rw}" height="20" fill="${top ? "#d9546b" : "#888"}"/>
<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">
<text x="8" y="14">footprint</text><text x="${lw + 6}" y="14">${right}</text></g></svg>`;
  return new Response(svg, {
    headers: { "Content-Type": "image/svg+xml", "Cache-Control": "public, max-age=3600" },
  });
}
