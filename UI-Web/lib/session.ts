import crypto from "node:crypto";
import { cookies } from "next/headers";

export type Session = { token: string; login: string };

const COOKIE = "fp_session";

function key() {
  const secret = process.env.SESSION_SECRET;
  if (!secret) throw new Error("SESSION_SECRET is not set");
  return crypto.scryptSync(secret, "footprint", 32);
}

export function seal(data: Session): string {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", key(), iv);
  const ct = Buffer.concat([
    cipher.update(JSON.stringify(data), "utf8"),
    cipher.final(),
  ]);
  return Buffer.concat([iv, cipher.getAuthTag(), ct]).toString("base64url");
}

export function unseal(sealed: string): Session | null {
  try {
    const buf = Buffer.from(sealed, "base64url");
    const decipher = crypto.createDecipheriv(
      "aes-256-gcm",
      key(),
      buf.subarray(0, 12),
    );
    decipher.setAuthTag(buf.subarray(12, 28));
    const pt = Buffer.concat([
      decipher.update(buf.subarray(28)),
      decipher.final(),
    ]);
    return JSON.parse(pt.toString("utf8"));
  } catch {
    return null;
  }
}

export async function getSession(): Promise<Session | null> {
  const raw = (await cookies()).get(COOKIE)?.value;
  return raw ? unseal(raw) : null;
}

export async function setSession(data: Session) {
  (await cookies()).set(COOKIE, seal(data), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
}

export async function clearSession() {
  (await cookies()).delete(COOKIE);
}
