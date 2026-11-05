import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError, errorText, isAbort, type AnalysisEvent, type Job } from "./api";

const POLL_MS = 2000;
const MAX_BACKOFF_MS = 30000;
const MAX_FAILURES = 8;
const STALL_MS = 10 * 60 * 1000;

export const isActive = (j: Job) => j.status === "queued" || j.status === "running";

/**
 * Job list with bounded polling: polls only while some job is queued/running,
 * never overlaps requests, pauses while the tab is hidden, backs off on errors,
 * stops after repeated failures or a long stall, and aborts on unmount/refresh.
 */
export function useJobs(enabled: boolean) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stopped, setStopped] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const ctrl = new AbortController();
    let failures = 0;
    let lastSig = "";
    let lastChange = Date.now();
    setStopped(null);

    const schedule = (ms: number) => {
      if (!cancelled) timer = setTimeout(run, ms);
    };

    async function run() {
      if (cancelled) return;
      if (document.hidden) return schedule(1000);
      try {
        const { items } = await api.jobs(50, ctrl.signal);
        if (cancelled) return;
        failures = 0;
        setError(null);
        setJobs(items);
        const active = items.filter(isActive);
        if (!active.length) return; // idle: wait for refresh()
        const sig = active.map((j) => `${j.id}:${j.status}:${j.progress}`).join("|");
        if (sig !== lastSig) {
          lastSig = sig;
          lastChange = Date.now();
        } else if (Date.now() - lastChange > STALL_MS) {
          setStopped("No job progress for 10 minutes; automatic refresh paused.");
          return;
        }
        schedule(POLL_MS);
      } catch (e) {
        if (cancelled || isAbort(e)) return;
        if (e instanceof ApiError && e.status === 401) return; // auth gate takes over
        failures++;
        setError(errorText(e));
        if (failures >= MAX_FAILURES) {
          setStopped("Job refresh stopped after repeated errors.");
          return;
        }
        schedule(Math.min(MAX_BACKOFF_MS, POLL_MS * 2 ** failures));
      }
    }

    run();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [enabled, tick]);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  /** Insert/replace a job we already know about (e.g. POST /v1/jobs response) and resume polling. */
  const upsert = useCallback((job: Job) => {
    setJobs((prev) => [job, ...(prev ?? []).filter((j) => j.id !== job.id)]);
    setTick((t) => t + 1);
  }, []);

  return { jobs, error, stopped, refresh, upsert };
}

export interface EventFilters {
  activity: string;
  object_class: string;
}

/** Paginated events for one completed job; resets on job/filter change. */
export function useEvents(jobId: string | null, ready: boolean, filters: EventFilters) {
  const [items, setItems] = useState<AnalysisEvent[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const gen = useRef(0);
  const ctrlRef = useRef<AbortController | null>(null);

  const load = useCallback(
    async (next: string | null, append: boolean) => {
      if (!jobId) return;
      const myGen = append ? gen.current : ++gen.current;
      ctrlRef.current?.abort();
      const ctrl = new AbortController();
      ctrlRef.current = ctrl;
      setLoading(true);
      setError(null);
      try {
        const page = await api.events(
          {
            job_id: jobId,
            activity: filters.activity || undefined,
            object_class: filters.object_class || undefined,
            cursor: next,
          },
          ctrl.signal,
        );
        if (myGen !== gen.current) return;
        setItems((prev) => (append ? [...prev, ...page.items] : page.items));
        setCursor(page.next_cursor);
      } catch (e) {
        if (isAbort(e) || myGen !== gen.current) return;
        setError(errorText(e));
      } finally {
        if (myGen === gen.current) setLoading(false);
      }
    },
    [jobId, filters.activity, filters.object_class],
  );

  useEffect(() => {
    gen.current++;
    setItems([]);
    setCursor(null);
    setError(null);
    setLoading(false);
    if (jobId && ready) load(null, false);
    return () => ctrlRef.current?.abort();
  }, [load, jobId, ready]);

  const loadMore = useCallback(() => {
    if (cursor && !loading) load(cursor, true);
  }, [cursor, loading, load]);

  const retry = useCallback(() => load(null, false), [load]);

  const patch = useCallback((id: string, p: Partial<AnalysisEvent>) => {
    setItems((prev) => prev.map((e) => (e.id === id ? { ...e, ...p } : e)));
  }, []);

  return { items, hasMore: cursor !== null, loading, error, loadMore, retry, patch };
}
