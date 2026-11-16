import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { createKey } from "@/lib/vault";

// CLI sign-in: `/login` in the footprint shell listens on 127.0.0.1:<port> and opens this page.
// Not signed in -> GitHub first (callback returns here). Signed in -> consent button -> POST mints a key
// and hands it to the local listener. The POST step stops other sites from minting keys via a link.

function parse(port: unknown, state: unknown) {
  const p = Number(port);
  const s = String(state ?? "");
  return Number.isInteger(p) && p >= 1024 && p <= 65535 && /^[a-f0-9]{16,64}$/.test(s) ? { port: p, state: s } : null;
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

export async function GET(req: Request) {
  const u = new URL(req.url);
  const q = parse(u.searchParams.get("port"), u.searchParams.get("state"));
  if (!q) return new Response("bad CLI login request", { status: 400 });

  const session = await getSession();
  if (!session) {
    (await cookies()).set("fp_cli", `port=${q.port}&state=${q.state}`, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 600,
    });
    redirect("/api/auth/login");
  }

  const page = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Authorize footprint CLI</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#2a1717;color:#f9ece1;font-family:system-ui,sans-serif}
main{padding:32px;max-width:360px;text-align:center}h1{font-size:20px}p{color:#c8a193}
button{background:#ff6d82;color:#2a1717;border:0;border-radius:8px;padding:12px 20px;font-size:15px;font-weight:600;cursor:pointer}</style>
<main><h1>Authorize footprint CLI</h1><p>Signed in as <b>${esc(session.login)}</b>. This creates an API key for the footprint shell on this computer.</p>
<form method="post"><input type="hidden" name="port" value="${q.port}"><input type="hidden" name="state" value="${q.state}">
<button type="submit">Authorize</button></form></main>`;
  return new Response(page, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}

export async function POST(req: Request) {
  const f = await req.formData();
  const q = parse(f.get("port"), f.get("state"));
  const session = await getSession();
  if (!q || !session) return new Response("bad CLI login request", { status: 400 });

  const key = await createKey(session.token, session.login, `cli ${new Date().toISOString().slice(0, 10)}`);
  const to = `http://127.0.0.1:${q.port}/callback?state=${q.state}&key=${encodeURIComponent(key)}`;
  return new Response(null, { status: 303, headers: { Location: to } });
}
