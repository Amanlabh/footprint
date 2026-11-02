import { parseRun } from "@/lib/bench";
import { appendBench, verifyKey } from "@/lib/vault";

/** `footprint bench upload`: Bearer fp_… + one run (numbers only) -> appended to the user's vault bench.json. */
export async function POST(req: Request) {
  const key = (req.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  const s = await verifyKey(key);
  if (!s) return Response.json({ error: "invalid or revoked key" }, { status: 401 });
  const body = await req.text();
  if (body.length > 20_000) return Response.json({ error: "payload too large" }, { status: 413 });
  let run;
  try {
    run = parseRun(JSON.parse(body));
  } catch {
    run = null;
  }
  if (!run) return Response.json({ error: "invalid bench run" }, { status: 400 });
  try {
    await appendBench(s.token, s.login, run);
  } catch (e) {
    return Response.json({ error: e instanceof Error ? e.message : "vault write failed" }, { status: 502 });
  }
  return Response.json({ ok: true, login: s.login });
}
