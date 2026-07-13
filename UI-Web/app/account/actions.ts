"use server";

import { revalidatePath } from "next/cache";
import { getSession } from "@/lib/session";
import { createKey, revokeKey } from "@/lib/vault";

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
