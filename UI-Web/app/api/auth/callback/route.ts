import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { setSession } from "@/lib/session";
import { ensureVault, getUser } from "@/lib/vault";

export async function GET(req: Request) {
  const url = new URL(req.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const jar = await cookies();
  const expected = jar.get("fp_oauth_state")?.value;
  jar.delete("fp_oauth_state");

  if (!code || !state || !expected || state !== expected)
    return new Response("OAuth state mismatch", { status: 400 });

  const res = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      client_id: process.env.GITHUB_CLIENT_ID?.trim(),
      client_secret: process.env.GITHUB_CLIENT_SECRET?.trim(),
      code,
      redirect_uri: new URL("/api/auth/callback", req.url).toString(),
    }),
  });
  const data = (await res.json()) as { access_token?: string };
  if (!data.access_token)
    return new Response("GitHub token exchange failed", { status: 400 });

  const { login } = await getUser(data.access_token);
  await ensureVault(data.access_token, login);
  await setSession({ token: data.access_token, login });
  redirect("/account");
}
