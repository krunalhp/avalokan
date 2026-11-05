import type { Job } from "../api";
import { fmtDate, fmtPct } from "../format";

interface Props {
  jobs: Job[] | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  error: string | null;
  stopped: string | null;
  onRefresh: () => void;
}

export function StatusBadge({ status }: { status: Job["status"] }) {
  return <span class={`badge status-${status}`}>{status}</span>;
}

export function JobList({ jobs, selectedId, onSelect, error, stopped, onRefresh }: Props) {
  return (
    <section class="panel-section jobs" aria-labelledby="jobs-title">
      <div class="row between">
        <h2 id="jobs-title" class="section-title">
          Clip library
        </h2>
        <button class="btn btn-ghost btn-sm" type="button" onClick={onRefresh} aria-label="Refresh job list">
          Refresh
        </button>
      </div>
      {(error || stopped) && (
        <p class="alert alert-warn small" role="status">
          {stopped ?? `Refresh failed: ${error}`}{" "}
          {stopped && (
            <button class="link" type="button" onClick={onRefresh}>
              Resume
            </button>
          )}
        </p>
      )}
      {jobs === null ? (
        <p class="muted small" aria-busy="true">
          Loading jobs…
        </p>
      ) : jobs.length === 0 ? (
        <p class="empty small">No analyses yet. Upload a clip to begin.</p>
      ) : (
        <ul class="job-list" aria-label="Analysis jobs, newest first">
          {jobs.map((j) => (
            <li key={j.id}>
              <button
                type="button"
                class={`job ${j.id === selectedId ? "selected" : ""}`}
                aria-pressed={j.id === selectedId}
                onClick={() => onSelect(j.id)}
              >
                <span class="row between">
                  <span class="job-name ellipsis" title={j.media_name}>
                    {j.media_name}
                  </span>
                  <StatusBadge status={j.status} />
                </span>
                <span class="row between small muted">
                  <span>{fmtDate(j.created_at)}</span>
                  <span>
                    {j.status === "completed"
                      ? `${j.event_count} event${j.event_count === 1 ? "" : "s"}`
                      : j.status === "failed"
                        ? "no results"
                        : fmtPct(j.progress)}
                  </span>
                </span>
                {(j.status === "queued" || j.status === "running") && (
                  <progress class="thin" max={1} value={j.progress} aria-label={`Progress for ${j.media_name}`} />
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
