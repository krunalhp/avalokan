import { useCallback, useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError, errorText, isAbort, onUnauthorized, type AnalysisEvent, type Capabilities, type Job } from "./api";
import { AuthDialog } from "./components/AuthDialog";
import { EventsPanel } from "./components/EventsPanel";
import { JobList } from "./components/JobList";
import { PlayerPanel } from "./components/PlayerPanel";
import { UploadForm } from "./components/UploadForm";
import { useEvents, useJobs, type EventFilters } from "./hooks";

/** Selected job lives in the URL fragment (#job=<id>) so a reload returns to it. Never holds credentials. */
function readHashJob(): string | null {
  const m = /^#job=([^&]+)/.exec(location.hash);
  return m ? decodeURIComponent(m[1]) : null;
}

const NO_FILTERS: EventFilters = { activity: "", object_class: "" };

export function App() {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [needAuth, setNeedAuth] = useState(false);
  const [bootTick, setBootTick] = useState(0);

  useEffect(() => {
    onUnauthorized(() => setNeedAuth(true));
    return () => onUnauthorized(null);
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    setBootError(null);
    api
      .capabilities(ctrl.signal)
      .then((c) => {
        setCaps(c);
        setNeedAuth(false);
      })
      .catch((e) => {
        if (isAbort(e) || (e instanceof ApiError && e.status === 401)) return;
        setBootError(errorText(e));
      });
    return () => ctrl.abort();
  }, [bootTick]);

  const { jobs, error: jobsError, stopped, refresh, upsert } = useJobs(!!caps && !needAuth);

  const [selectedJobId, setSelectedJobId] = useState<string | null>(readHashJob);
  const [fallbackJob, setFallbackJob] = useState<Job | null>(null);
  const [filters, setFilters] = useState<EventFilters>(NO_FILTERS);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);

  const selectJob = useCallback((id: string | null) => {
    setSelectedJobId(id);
    setFilters(NO_FILTERS);
    setSelectedEventId(null);
    setCurrentTime(0);
    history.replaceState(null, "", id ? `#job=${encodeURIComponent(id)}` : location.pathname + location.search);
  }, []);

  useEffect(() => {
    const onHash = () => {
      const id = readHashJob();
      if (id !== selectedJobId) selectJob(id);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [selectedJobId, selectJob]);

  // A job selected via URL may be older than the 50 listed; fetch it directly.
  const listed = jobs?.find((j) => j.id === selectedJobId) ?? null;
  useEffect(() => {
    setFallbackJob(null);
    if (!selectedJobId || !jobs || listed || needAuth) return;
    const ctrl = new AbortController();
    api
      .job(selectedJobId, ctrl.signal)
      .then(setFallbackJob)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, [selectedJobId, !!jobs, !!listed, needAuth]);
  const job = listed ?? fallbackJob;

  const events = useEvents(job?.id ?? null, job?.status === "completed", filters);

  const seek = useCallback((t: number) => {
    const v = videoRef.current;
    if (!v) return;
    if (v.readyState >= 1) v.currentTime = t;
    else v.addEventListener("loadedmetadata", () => (v.currentTime = t), { once: true });
    v.focus({ preventScroll: true });
  }, []);

  const selectEvent = useCallback(
    (ev: AnalysisEvent) => {
      setSelectedEventId(ev.id);
      seek(ev.start_s);
    },
    [seek],
  );

  const onJobCreated = useCallback(
    (j: Job) => {
      upsert(j);
      selectJob(j.id);
    },
    [upsert, selectJob],
  );

  async function signOut() {
    try {
      await api.deleteSession();
    } catch {
      /* the cookie may already be gone */
    }
    setNeedAuth(true);
  }

  const reauth = () => {
    setNeedAuth(false);
    setBootTick((t) => t + 1);
  };

  if (!caps) {
    return (
      <div class="boot">
        {needAuth ? (
          <AuthDialog onAuthenticated={reauth} />
        ) : bootError ? (
          <div class="empty-state" role="alert">
            <h1>Cannot reach the Avalokan API</h1>
            <p class="muted">{bootError}</p>
            <button class="btn btn-primary" type="button" onClick={() => setBootTick((t) => t + 1)}>
              Try again
            </button>
          </div>
        ) : (
          <p class="muted" aria-busy="true">
            Connecting to the Avalokan API…
          </p>
        )}
      </div>
    );
  }

  const demo = /demo/i.test(caps.access_mode);

  return (
    <div class="app">
      <header class="topbar">
        <div class="brand">
          <span class="logo" aria-hidden="true" />
          <span>
            <strong>Avalokan</strong> <span class="muted">Clip workbench</span>
          </span>
        </div>
        <div class="row gap-sm wrap-row">
          {demo ? (
            <span class="badge badge-warn" title="AVALOKAN_DEMO=1: authentication is disabled">
              Demo mode · no auth
            </span>
          ) : (
            <span class="badge">{caps.access_mode}</span>
          )}
          <span
            class={`badge ${caps.model.ready ? "badge-ok" : "badge-warn"}`}
            title={`Model SHA-256: ${caps.model.sha256}`}
          >
            {caps.model.name} {caps.model.ready ? "ready" : "not ready"}
          </span>
          <a class="btn btn-ghost btn-sm" href="/docs" target="_blank" rel="noopener">
            API docs
          </a>
          {!demo && (
            <button class="btn btn-ghost btn-sm" type="button" onClick={signOut}>
              Sign out
            </button>
          )}
        </div>
      </header>

      <div class="workbench">
        <aside class="col col-left" aria-label="Clip library and upload">
          <UploadForm caps={caps} selectedJob={job} onJobCreated={onJobCreated} />
          <JobList
            jobs={jobs}
            selectedId={selectedJobId}
            onSelect={selectJob}
            error={jobsError}
            stopped={stopped}
            onRefresh={refresh}
          />
        </aside>
        <main class="col col-center">
          <PlayerPanel
            job={job}
            videoRef={videoRef}
            events={events.items}
            selectedEventId={selectedEventId}
            currentTime={currentTime}
            onSelectEvent={selectEvent}
            onTimeUpdate={setCurrentTime}
          />
        </main>
        <aside class="col col-right" aria-label="Events and review">
          <EventsPanel
            job={job}
            caps={caps}
            events={events}
            filters={filters}
            onFilters={(f) => {
              setFilters(f);
              setSelectedEventId(null);
            }}
            selectedId={selectedEventId}
            onSelect={selectEvent}
            onSeek={seek}
            currentTime={currentTime}
          />
        </aside>
      </div>

      {needAuth && <AuthDialog onAuthenticated={reauth} />}
    </div>
  );
}
