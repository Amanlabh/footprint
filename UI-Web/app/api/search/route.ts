import { verifyKey } from "@/lib/vault";

/** `footprint ask` web search: Bearer fp_… + ?q= -> Brave results. The Brave key (BRAVE_API_KEY) stays on the
 *  server; users never see it. Queries are not stored or logged. */
const DAILY = Number(process.env.SEARCH_DAILY_LIMIT ?? 100);
// ponytail: per-instance memory, so the limit is per server instance and resets on cold start.
// Move to Upstash Redis (Vercel Marketplace) if one user's volume ever matters.
const used = new Map<string, { day: string; n: number }>();

type BraveHit = { title?: string; url?: string; description?: string };

export async function GET(req: Request) {
  const s = await verifyKey((req.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, ""));
  if (!s) return Response.json({ error: "invalid or revoked key" }, { status: 401 });
  const q = new URL(req.url).searchParams.get("q")?.trim().slice(0, 400);
  if (!q) return Response.json({ error: "missing q" }, { status: 400 });
  const brave = process.env.BRAVE_API_KEY;
  if (!brave) return Response.json({ error: "web search is not configured on the server" }, { status: 503 });

  const day = new Date().toISOString().slice(0, 10);
  const u = used.get(s.login);
  const n = u?.day === day ? u.n : 0;
  if (n >= DAILY) return Response.json({ error: `daily search limit (${DAILY}) reached` }, { status: 429 });
  used.set(s.login, { day, n: n + 1 });

  const r = await fetch(`https://api.search.brave.com/res/v1/web/search?count=5&q=${encodeURIComponent(q)}`, {
    headers: { "X-Subscription-Token": brave, Accept: "application/json" },
  });
  if (!r.ok) return Response.json({ error: `search provider error ${r.status}` }, { status: 502 });
  const d = (await r.json()) as { web?: { results?: BraveHit[] } };
  const results = (d.web?.results ?? []).map(({ title, url, description }) => ({ title, url, description }));
  return Response.json({ results });
}
