import crypto from "node:crypto";
import { seal, unseal, type Session } from "./session";

export const VAULT_REPO = "footprint-vault";
const API = "https://api.github.com";

export type ApiKey = {
  prefix: string; // first chars of the key, for display
  hash: string; // sha256 of the full key
  label: string;
  created: string;
};

async function gh(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  return fetch(`${API}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...init.headers,
    },
    cache: "no-store",
  });
}

export async function getUser(token: string): Promise<{ login: string }> {
  const res = await gh(token, "/user");
  if (!res.ok) throw new Error(`GitHub /user failed: ${res.status}`);
  return res.json();
}

/** Create the private vault repo in the user's account if it doesn't exist. */
export async function ensureVault(token: string, login: string) {
  const res = await gh(token, `/repos/${login}/${VAULT_REPO}`);
  if (res.ok) return;
  if (res.status !== 404)
    throw new Error(`GitHub repo check failed: ${res.status}`);
  const create = await gh(token, "/user/repos", {
    method: "POST",
    body: JSON.stringify({
      name: VAULT_REPO,
      private: true,
      auto_init: true,
      description:
        "footprint personal environment — API keys + synced context. Managed by footprint; keep private.",
    }),
  });
  if (!create.ok)
    throw new Error(`Could not create vault repo: ${create.status}`);
}

async function readKeysFile(
  token: string,
  login: string,
): Promise<{ keys: ApiKey[]; sha: string | null }> {
  const res = await gh(
    token,
    `/repos/${login}/${VAULT_REPO}/contents/keys.json`,
  );
  if (res.status === 404) return { keys: [], sha: null };
  if (!res.ok) throw new Error(`Could not read keys.json: ${res.status}`);
  const data = (await res.json()) as { content: string; sha: string };
  const keys = JSON.parse(
    Buffer.from(data.content, "base64").toString("utf8"),
  ) as ApiKey[];
  return { keys, sha: data.sha };
}

async function writeKeysFile(
  token: string,
  login: string,
  keys: ApiKey[],
  sha: string | null,
  message: string,
) {
  const res = await gh(
    token,
    `/repos/${login}/${VAULT_REPO}/contents/keys.json`,
    {
      method: "PUT",
      body: JSON.stringify({
        message,
        content: Buffer.from(JSON.stringify(keys, null, 2)).toString("base64"),
        ...(sha ? { sha } : {}),
      }),
    },
  );
  if (!res.ok) throw new Error(`Could not write keys.json: ${res.status}`);
}

export async function listKeys(token: string, login: string) {
  await ensureVault(token, login);
  return (await readKeysFile(token, login)).keys;
}

const sha256 = (s: string) => crypto.createHash("sha256").update(s).digest("hex");

/**
 * Key = "fp_" + sealed {token, login}: the server learns who you are from the
 * key alone, no database. Revocation = hash removed from the user's keys.json.
 * ponytail: one GitHub read per verify; cache it when the model gateway lands.
 * Rotating SESSION_SECRET invalidates every key.
 */
export async function verifyKey(key: string): Promise<Session | null> {
  if (!key.startsWith("fp_")) return null;
  const s = unseal(key.slice(3));
  if (!s) return null;
  try {
    const { keys } = await readKeysFile(s.token, s.login);
    return keys.some((k) => k.hash === sha256(key)) ? s : null;
  } catch {
    return null;
  }
}

/** Generate a key, store only its hash in the vault. Returns plaintext once. */
export async function createKey(token: string, login: string, label: string) {
  await ensureVault(token, login);
  const plaintext = `fp_${seal({ token, login })}`;
  const entry: ApiKey = {
    prefix: plaintext.slice(0, 11),
    hash: sha256(plaintext),
    label: label || "unnamed",
    created: new Date().toISOString(),
  };
  const { keys, sha } = await readKeysFile(token, login);
  await writeKeysFile(
    token,
    login,
    [...keys, entry],
    sha,
    `footprint: add API key ${entry.prefix}… (${entry.label})`,
  );
  return plaintext;
}

export async function revokeKey(token: string, login: string, prefix: string) {
  const { keys, sha } = await readKeysFile(token, login);
  const next = keys.filter((k) => k.prefix !== prefix);
  if (next.length === keys.length) return;
  await writeKeysFile(
    token,
    login,
    next,
    sha,
    `footprint: revoke API key ${prefix}…`,
  );
}
