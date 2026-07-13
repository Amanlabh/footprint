import crypto from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export async function GET(req: Request) {
  const clientId = process.env.GITHUB_CLIENT_ID;
  if (!clientId) return new Response("GITHUB_CLIENT_ID not set", { status: 500 });

  const state = crypto.randomBytes(16).toString("hex");
  (await cookies()).set("fp_oauth_state", state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 600,
  });

  const url = new URL("https://github.com/login/oauth/authorize");
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("redirect_uri", new URL("/api/auth/callback", req.url).toString());
  url.searchParams.set("scope", "repo read:user");
  url.searchParams.set("state", state);
  redirect(url.toString());
}
