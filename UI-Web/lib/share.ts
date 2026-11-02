import { parseRun, type BenchRun, type SharedBench } from "./bench";
import { seal, unseal } from "./session";

const PURPOSE = "footprint-share"; // own key: a share link can't be opened as an API key or session

/**
 * Opt-in public share link: the summary itself is sealed into the URL, so there is no
 * database and nothing public until the user clicks Share.
 * ponytail: links can't be revoked individually (stateless); rotating SESSION_SECRET kills all.
 */
export function shareToken(login: string, run: BenchRun) {
  const rows = [...run.rows].sort((a, b) => b.passed - a.passed).slice(0, 5);
  return seal({ login, date: run.date, tasks: run.tasks, rows }, PURPOSE);
}

export function readShare(token: string): SharedBench | null {
  const raw = unseal<Record<string, unknown>>(token, PURPOSE);
  const run = parseRun(raw);
  const login = raw?.login;
  if (!run || typeof login !== "string" || !/^[\w-]{1,39}$/.test(login)) return null;
  return { login, ...run };
}
