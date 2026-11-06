// Typed client for the frozen Workbench API v1 (specs/002-clip-workbench/contracts/api.md).
// Same-origin only. Credentials travel as an HttpOnly cookie set by POST /v1/session;
// the token is never stored by this app and never placed in a URL.

export type ActivityStatus = string; // e.g. "experimental"

export interface Activity {
  id: string;
  name: string;
  description: string;
  status: ActivityStatus;
}

export interface Capabilities {
  activities: Activity[];
  classes: string[];
  config_schema: Record<string, unknown>;
  model: { name: string; sha256: string; ready: boolean };
  access_mode: string;
  url_ingest?: boolean;
  max_upload_bytes: number;
  max_duration_s: number;
}

export interface Media {
  id: string;
  name: string;
  duration_s: number;
  width: number;
  height: number;
  codec: string;
  size_bytes: number;
  sha256: string;
  playback_ready?: boolean;
}

export type Zone = [number, number, number, number];

export interface JobConfig {
  allowed_activities: string[];
  classes?: string[];
  sample_fps?: 1 | 2 | 5;
  confidence?: number;
  dwell_seconds?: number;
  line_x?: number;
  zone?: Zone;
}

export type JobStatus = "queued" | "running" | "completed" | "failed";

/** Progress of a remote-URL (e.g. YouTube) ingest, polled while downloading. */
export interface MediaIngest {
  id: string;
  url: string;
  status: "downloading" | "ready" | "failed";
  error: string | null;
  media: Media | null;
  created_at: string;
}

export interface Job {
  id: string;
  media_id: string;
  media_name: string;
  status: JobStatus;
  progress: number;
  config: JobConfig;
  error: string | null;
  stats: Record<string, unknown>;
  created_at: string;
  finished_at: string | null;
  event_count: number;
}

export type ReviewVerdict = "confirmed" | "rejected" | "uncertain";
export type ReviewStatus = "unreviewed" | ReviewVerdict;

export interface Review {
  id: string;
  verdict: ReviewVerdict;
  note: string;
  created_at: string;
}

export interface AnalysisEvent {
  id: string;
  job_id: string;
  activity: string;
  object_class: string;
  track_id: string | number | null;
  start_s: number;
  end_s: number;
  summary: string;
  confidence: number | null;
  attributes: Record<string, unknown>;
  provenance: Record<string, unknown>;
  review_status: ReviewStatus;
}

export interface EventDetail extends AnalysisEvent {
  reviews: Review[];
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Called whenever the API answers 401 so the app can show token entry. */
let unauthorizedHandler: (() => void) | null = null;
export function onUnauthorized(fn: (() => void) | null): void {
  unauthorizedHandler = fn;
}

function describeDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI/Pydantic validation errors: [{loc, msg, type}]
    const parts = detail.map((d) => {
      if (d && typeof d === "object") {
        const o = d as { loc?: unknown[]; msg?: unknown };
        const loc = Array.isArray(o.loc) ? o.loc.filter((x) => x !== "body").join(".") : "";
        const msg = typeof o.msg === "string" ? o.msg : JSON.stringify(d);
        return loc ? `${loc}: ${msg}` : msg;
      }
      return String(d);
    });
    return parts.join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return null;
}

async function errorFrom(res: Response): Promise<ApiError> {
  let message = `${res.status} ${res.statusText || "request failed"}`;
  try {
    const body = (await res.json()) as { detail?: unknown };
    const d = describeDetail(body?.detail);
    if (d) message = d;
  } catch {
    /* non-JSON error body */
  }
  if (res.status === 401) unauthorizedHandler?.();
  return new ApiError(res.status, message);
}

async function request<T>(
  method: string,
  path: string,
  opts: { body?: unknown; headers?: Record<string, string>; signal?: AbortSignal } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  let body: BodyInit | undefined;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, {
    method,
    headers,
    body,
    credentials: "same-origin",
    signal: opts.signal,
  });
  if (!res.ok) throw await errorFrom(res);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

const enc = encodeURIComponent;

export function newIdempotencyKey(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // randomUUID requires a secure context; fall back to an RFC 4122 v4 UUID.
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export const api = {
  createSession: (token: string) => request<unknown>("POST", "/v1/session", { body: { token } }),
  deleteSession: () => request<unknown>("DELETE", "/v1/session"),

  capabilities: (signal?: AbortSignal) => request<Capabilities>("GET", "/v1/capabilities", { signal }),

  media: (id: string, signal?: AbortSignal) => request<Media>("GET", `/v1/media/${enc(id)}`, { signal }),
  videoUrl: (id: string) => `/v1/media/${enc(id)}/video`,

  ingestUrl: (url: string, idempotencyKey: string, signal?: AbortSignal) =>
    request<MediaIngest>("POST", "/v1/media/url", {
      body: { url },
      headers: { "Idempotency-Key": idempotencyKey },
      signal,
    }),
  ingest: (id: string, signal?: AbortSignal) =>
    request<MediaIngest>("GET", `/v1/media-ingests/${enc(id)}`, { signal }),

  /** Multipart upload with progress, via XHR (fetch has no upload progress). */
  uploadMedia(file: File, onProgress: (fraction: number) => void, signal: AbortSignal): Promise<Media> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/v1/media");
      xhr.setRequestHeader("Accept", "application/json");
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText) as Media);
          } catch {
            reject(new ApiError(xhr.status, "Upload succeeded but the response was not JSON"));
          }
          return;
        }
        let message = `${xhr.status} upload failed`;
        if (xhr.status === 413) message = "File exceeds the server upload limit (413).";
        try {
          const d = describeDetail((JSON.parse(xhr.responseText) as { detail?: unknown }).detail);
          if (d) message = d;
        } catch {
          /* ignore */
        }
        if (xhr.status === 401) unauthorizedHandler?.();
        reject(new ApiError(xhr.status, message));
      };
      xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
      xhr.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
      const form = new FormData();
      form.append("file", file, file.name);
      xhr.send(form);
    });
  },

  createJob: (mediaId: string, config: JobConfig, idempotencyKey: string) =>
    request<Job>("POST", "/v1/jobs", {
      body: { media_id: mediaId, config },
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  jobs: (limit = 50, signal?: AbortSignal) => request<{ items: Job[] }>("GET", `/v1/jobs${qs({ limit })}`, { signal }),
  job: (id: string, signal?: AbortSignal) => request<Job>("GET", `/v1/jobs/${enc(id)}`, { signal }),

  events: (
    p: { job_id: string; activity?: string; object_class?: string; cursor?: string | null; limit?: number },
    signal?: AbortSignal,
  ) => request<Page<AnalysisEvent>>("GET", `/v1/events${qs({ limit: 100, ...p })}`, { signal }),
  event: (id: string, signal?: AbortSignal) => request<EventDetail>("GET", `/v1/events/${enc(id)}`, { signal }),
  addReview: (id: string, verdict: ReviewVerdict, note: string) =>
    request<Review>("POST", `/v1/events/${enc(id)}/reviews`, { body: { verdict, note } }),
};

export function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}
