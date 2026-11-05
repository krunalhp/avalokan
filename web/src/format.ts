/** Relative source seconds → m:ss.s (or h:mm:ss.s). Never implies wall-clock time. */
export function fmtTime(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s)) return "–";
  const neg = s < 0;
  let t = Math.abs(s);
  const h = Math.floor(t / 3600);
  t -= h * 3600;
  const m = Math.floor(t / 60);
  const sec = t - m * 60;
  const ss = sec.toFixed(1).padStart(4, "0");
  const body = h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
  return neg ? `-${body}` : body;
}

export function fmtRange(start: number, end: number): string {
  return start === end ? `@ ${fmtTime(start)}` : `${fmtTime(start)} – ${fmtTime(end)}`;
}

export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "–";
  const units = ["B", "KiB", "MiB", "GiB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function fmtPct(f: number | null | undefined): string {
  if (f === null || f === undefined || !Number.isFinite(f)) return "–";
  return `${Math.round(Math.max(0, Math.min(1, f)) * 100)}%`;
}

/** Human-friendly rendering of arbitrary JSON values from stats/attributes/provenance. */
export function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3).replace(/\.?0+$/, "");
  if (typeof v === "string" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

export function shortHash(h: unknown): string {
  return typeof h === "string" && h.length > 16 ? `${h.slice(0, 12)}…` : fmtValue(h);
}

export function humanize(key: string): string {
  return key.replace(/[_.]+/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
