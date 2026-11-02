"use server";

import { revalidatePath } from "next/cache";
import { getSession } from "@/lib/session";
import { createKey, readBench, revokeKey } from "@/lib/vault";
import { shareToken } from "@/lib/share";

export async function generateKeyAction(
  _prev: { key: string | null; error: string | null },
  formData: FormData,
): Promise<{ key: string | null; error: string | null }> {
  const session = await getSession();
  if (!session) return { key: null, error: "Not signed in." };
  try {
    const key = await createKey(
      session.token,
      session.login,
      String(formData.get("label") ?? "").trim(),
    );
    revalidatePath("/account");
    return { key, error: null };
  } catch (e) {
    return { key: null, error: e instanceof Error ? e.message : "Failed." };
  }
}

export async function revokeKeyAction(formData: FormData) {
  const session = await getSession();
  if (!session) return;
  await revokeKey(session.token, session.login, String(formData.get("prefix")));
  revalidatePath("/account");
}

/** Opt-in: make a public link + badge for the latest bench run. */
export async function shareBenchAction(): Promise<{ path: string | null; error: string | null }> {
  const session = await getSession();
  if (!session) return { path: null, error: "Not signed in." };
  try {
    const runs = await readBench(session.token, session.login);
    if (!runs.length) return { path: null, error: "No bench results yet." };
    return { path: `/share/${shareToken(session.login, runs[runs.length - 1])}`, error: null };
  } catch (e) {
    return { path: null, error: e instanceof Error ? e.message : "Failed." };
  }
}
