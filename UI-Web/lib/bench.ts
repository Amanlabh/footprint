/** footprint bench results: numbers only — model names, scores, counts, date. Never prompts or code. */

export type BenchRow = {
  model: string;
  memory: boolean;
  passed: number;
  total: number;
  overlap: number; // 0..1 share of files also changed by Claude
  seconds: number;
  tokens: number;
};
export type BenchRun = { date: string; tasks: number; rows: BenchRow[] };
export type SharedBench = { login: string } & BenchRun;

const int = (v: unknown, max: number) =>
  typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= max;
const num = (v: unknown, max: number) =>
  typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= max;

/** Strict parse of an uploaded run (trust boundary). Unknown fields are dropped. */
export function parseRun(x: unknown): BenchRun | null {
  if (!x || typeof x !== "object") return null;
  const r = x as Record<string, unknown>;
  if (typeof r.date !== "string" || !/^\d{4}-\d\d-\d\dT[\d:.]+Z$/.test(r.date)) return null;
  if (!int(r.tasks, 1000) || !Array.isArray(r.rows) || r.rows.length > 20) return null;
  const rows: BenchRow[] = [];
  for (const raw of r.rows) {
    const o = (raw ?? {}) as Record<string, unknown>;
    if (
      typeof o.model !== "string" ||
      !/^[\w.:+@/-]{1,80}$/.test(o.model) ||
      typeof o.memory !== "boolean" ||
      !int(o.total, 1000) ||
      !int(o.passed, o.total as number) ||
      !num(o.overlap, 1) ||
      !num(o.seconds, 1e6) ||
      !int(o.tokens, 1e9)
    )
      return null;
    rows.push({
      model: o.model,
      memory: o.memory,
      passed: o.passed as number,
      total: o.total as number,
      overlap: o.overlap as number,
      seconds: o.seconds as number,
      tokens: o.tokens as number,
    });
  }
  return { date: r.date, tasks: r.tasks as number, rows };
}

export const parity = (r: BenchRow) =>
  r.total ? Math.round((100 * r.passed) / r.total) : 0;

export const label = (r: BenchRow) => r.model + (r.memory ? " + memory" : "");

export const best = (run: BenchRun) =>
  [...run.rows].sort((a, b) => b.passed - a.passed || a.seconds - b.seconds)[0];

if (process.env.FOOTPRINT_SELFTEST) {
  // node --experimental-strip-types lib/bench.ts with FOOTPRINT_SELFTEST=1
  const ok = {
    date: "2026-11-02T10:00:00Z",
    tasks: 2,
    rows: [{ model: "opencode/big-pickle", memory: true, passed: 1, total: 2, overlap: 0.5, seconds: 30, tokens: 900, extra: "x" }],
  };
  const p = parseRun(ok);
  if (!p || "extra" in p.rows[0] || parity(p.rows[0]) !== 50) throw new Error("parse ok");
  for (const bad of [
    { ...ok, date: "yesterday" },
    { ...ok, rows: [{ ...ok.rows[0], passed: 3 }] },
    { ...ok, rows: [{ ...ok.rows[0], model: "<script>" }] },
    { ...ok, rows: Array(21).fill(ok.rows[0]) },
  ])
    if (parseRun(bad)) throw new Error("accepted bad: " + JSON.stringify(bad).slice(0, 80));
  console.log("bench.ts self-check ok");
}
