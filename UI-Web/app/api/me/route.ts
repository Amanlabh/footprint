import { verifyKey } from "@/lib/vault";

/** CLI key check: `Authorization: Bearer fp_…` → { login }. Never returns the GitHub token. */
export async function GET(req: Request) {
  const key = (req.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  const s = await verifyKey(key);
  return s
    ? Response.json({ login: s.login })
    : Response.json({ error: "invalid or revoked key" }, { status: 401 });
}
