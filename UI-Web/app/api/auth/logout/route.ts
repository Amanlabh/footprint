import { redirect } from "next/navigation";
import { clearSession } from "@/lib/session";

export async function POST() {
  await clearSession();
  redirect("/");
}
