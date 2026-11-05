import { useEffect, useState } from "preact/hooks";
import {
  api,
  errorText,
  isAbort,
  type AnalysisEvent,
  type Capabilities,
  type EventDetail,
  type Job,
  type ReviewStatus,
  type ReviewVerdict,
} from "../api";
import { fmtDate, fmtRange, fmtTime, fmtValue, humanize } from "../format";
import type { EventFilters } from "../hooks";

interface EventsState {
  items: AnalysisEvent[];
  hasMore: boolean;
  loading: boolean;
  error: string | null;
  loadMore: () => void;
  retry: () => void;
  patch: (id: string, p: Partial<AnalysisEvent>) => void;
}

interface Props {
  job: Job | null;
  caps: Capabilities;
  events: EventsState;
  filters: EventFilters;
  onFilters: (f: EventFilters) => void;
  selectedId: string | null;
  onSelect: (e: AnalysisEvent) => void;
  onSeek: (t: number) => void;
  currentTime: number;
}

const VERDICTS: ReviewVerdict[] = ["confirmed", "rejected", "uncertain"];

function ReviewBadge({ status }: { status: ReviewStatus }) {
  return <span class={`badge review-${status}`}>{status}</span>;
}

function KV({ data, label }: { data: Record<string, unknown> | undefined; label: string }) {
  const entries = Object.entries(data ?? {});
  if (!entries.length) return <p class="muted small">No {label.toLowerCase()} recorded.</p>;
  return (
    <dl class="kv" aria-label={label}>
      {entries.map(([k, v]) => (
        <div key={k}>
          <dt>{humanize(k)}</dt>
          <dd>{typeof v === "object" && v !== null ? <code class="wrap">{JSON.stringify(v)}</code> : fmtValue(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

function isActiveAt(e: AnalysisEvent, t: number) {
  return e.start_s === e.end_s ? Math.abs(t - e.start_s) < 0.5 : t >= e.start_s && t < e.end_s;
}

export function EventsPanel(p: Props) {
  const { job, caps, events, filters, onFilters } = p;
  const activityName = (id: string) => caps.activities.find((a) => a.id === id)?.name || id;

  if (!job) {
    return (
      <section class="panel-section" aria-label="Events">
        <h2 class="section-title">Events</h2>
        <p class="empty small">Select a job to review its events.</p>
      </section>
    );
  }

  const activityOptions = job.config.allowed_activities ?? [];
  const classOptions = job.config.classes ?? caps.classes;
  const selected = events.items.find((e) => e.id === p.selectedId) ?? null;

  return (
    <section class="panel-section events" aria-labelledby="events-title">
      <div class="row between">
        <h2 id="events-title" class="section-title">
          Events
        </h2>
        {job.status === "completed" && (
          <span class="small muted">
            {events.items.length}
            {events.hasMore ? "+" : ""} shown · {job.event_count} total
          </span>
        )}
      </div>
      <p class="hint-warn small">
        Experimental detectors and rules. Scores are model support, not calibrated probability, and never identify a
        person.
      </p>

      {job.status !== "completed" ? (
        <p class="empty small" aria-live="polite">
          {job.status === "failed"
            ? "This run failed; no events were published."
            : "Events appear when analysis completes — results are published all at once."}
        </p>
      ) : (
        <>
          <div class="grid-2 filters">
            <label class="field">
              <span>Activity</span>
              <select
                value={filters.activity}
                onChange={(e) => onFilters({ ...filters, activity: (e.currentTarget as HTMLSelectElement).value })}
              >
                <option value="">All activities</option>
                {activityOptions.map((a) => (
                  <option key={a} value={a}>
                    {activityName(a)}
                  </option>
                ))}
              </select>
            </label>
            <label class="field">
              <span>Object class</span>
              <select
                value={filters.object_class}
                onChange={(e) => onFilters({ ...filters, object_class: (e.currentTarget as HTMLSelectElement).value })}
              >
                <option value="">All classes</option>
                {classOptions.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {events.error && (
            <p class="alert alert-error small" role="alert">
              {events.error}{" "}
              <button class="link" type="button" onClick={events.retry}>
                Retry
              </button>
            </p>
          )}

          {events.items.length === 0 && !events.loading && !events.error ? (
            <p class="empty small">
              {activityOptions.length === 0
                ? "No activities were enabled for this run (deny-all), so no events exist."
                : filters.activity || filters.object_class
                  ? "No events match these filters."
                  : "The run completed without emitting events."}
            </p>
          ) : (
            <ul class="event-list" aria-label="Events" aria-busy={events.loading}>
              {events.items.map((ev) => (
                <li key={ev.id}>
                  <button
                    type="button"
                    class={`event ${ev.id === p.selectedId ? "selected" : ""} ${isActiveAt(ev, p.currentTime) ? "active" : ""}`}
                    aria-pressed={ev.id === p.selectedId}
                    onClick={() => p.onSelect(ev)}
                  >
                    <span class="row between">
                      <span class="event-title ellipsis">
                        {activityName(ev.activity)} · {ev.object_class}
                      </span>
                      <ReviewBadge status={ev.review_status} />
                    </span>
                    <span class="row between small muted">
                      <span class="mono">{fmtRange(ev.start_s, ev.end_s)}</span>
                      <span>
                        {ev.track_id !== null && ev.track_id !== undefined ? `track ${ev.track_id}` : ""}
                        {ev.confidence !== null && ev.confidence !== undefined ? ` · score ${ev.confidence.toFixed(2)}` : ""}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {events.loading && (
            <p class="muted small" aria-live="polite">
              Loading events…
            </p>
          )}
          {events.hasMore && !events.loading && (
            <button class="btn btn-sm" type="button" onClick={events.loadMore}>
              Load more events
            </button>
          )}

          {selected && (
            <EventDetailView
              key={selected.id}
              event={selected}
              activityName={activityName(selected.activity)}
              activityStatus={caps.activities.find((a) => a.id === selected.activity)?.status}
              onSeek={p.onSeek}
              onReviewed={(status) => events.patch(selected.id, { review_status: status })}
            />
          )}
        </>
      )}
    </section>
  );
}

function EventDetailView(props: {
  event: AnalysisEvent;
  activityName: string;
  activityStatus?: string;
  onSeek: (t: number) => void;
  onReviewed: (s: ReviewStatus) => void;
}) {
  const { event } = props;
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [verdict, setVerdict] = useState<ReviewVerdict | null>(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setError(null);
    api
      .event(event.id, ctrl.signal)
      .then((d) => {
        setDetail(d);
        if (d.review_status && d.review_status !== event.review_status) props.onReviewed(d.review_status);
      })
      .catch((e) => {
        if (!isAbort(e)) setError(errorText(e));
      });
    return () => ctrl.abort();
  }, [event.id, tick]);

  async function submit(e: Event) {
    e.preventDefault();
    if (!verdict) {
      setSaveError("Choose a verdict.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await api.addReview(event.id, verdict, note.trim());
      setNote("");
      setVerdict(null);
      // Latest review drives the list badge; reload detail for the authoritative history.
      props.onReviewed(verdict);
      setTick((t) => t + 1);
    } catch (err) {
      setSaveError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  const prov = detail?.provenance ?? event.provenance;
  const experimental =
    (props.activityStatus && props.activityStatus !== "stable") ||
    Object.entries(prov ?? {}).some(([k, v]) => /experimental/i.test(k) || v === "experimental");
  const reviews = detail ? [...detail.reviews].sort((a, b) => b.created_at.localeCompare(a.created_at)) : [];

  return (
    <article class="event-detail" aria-labelledby="event-detail-title">
      <div class="row between">
        <h3 id="event-detail-title">
          {props.activityName} · {event.object_class}
        </h3>
        <button class="btn btn-sm" type="button" onClick={() => props.onSeek(event.start_s)}>
          Seek to {fmtTime(event.start_s)}
        </button>
      </div>
      {event.summary && <p class="summary">{event.summary}</p>}
      {experimental && (
        <p class="alert alert-warn small">
          Experimental{props.activityStatus ? ` (${props.activityStatus})` : ""}: not validated on labeled,
          scene-separated data. Verify against the video before relying on it.
        </p>
      )}
      <dl class="kv">
        <div>
          <dt>Source time</dt>
          <dd class="mono">
            {fmtRange(event.start_s, event.end_s)} {event.start_s === event.end_s ? "(point)" : "(observed interval)"}
          </dd>
        </div>
        <div>
          <dt>Track</dt>
          <dd>{fmtValue(event.track_id)}</dd>
        </div>
        <div>
          <dt>Model score</dt>
          <dd>{event.confidence === null ? "–" : `${event.confidence.toFixed(3)} (uncalibrated)`}</dd>
        </div>
        <div>
          <dt>Event ID</dt>
          <dd>
            <code class="wrap">{event.id}</code>
          </dd>
        </div>
      </dl>
      <details>
        <summary class="small">Attributes</summary>
        <KV data={detail?.attributes ?? event.attributes} label="Attributes" />
      </details>
      <details open>
        <summary class="small">Provenance</summary>
        <KV data={prov} label="Provenance" />
      </details>

      <h4>Human review</h4>
      {error && (
        <p class="alert alert-error small" role="alert">
          {error}{" "}
          <button class="link" type="button" onClick={() => setTick((t) => t + 1)}>
            Retry
          </button>
        </p>
      )}
      {!detail && !error && <p class="muted small">Loading review history…</p>}
      {detail && reviews.length === 0 && <p class="muted small">Not reviewed yet.</p>}
      {reviews.length > 0 && (
        <ol class="reviews" aria-label="Review history, newest first">
          {reviews.map((r) => (
            <li key={r.id}>
              <span class="row between small">
                <ReviewBadge status={r.verdict} />
                <span class="muted">{fmtDate(r.created_at)}</span>
              </span>
              {r.note && <p class="small">{r.note}</p>}
            </li>
          ))}
        </ol>
      )}
      <form class="review-form" onSubmit={submit}>
        <fieldset class="segmented" disabled={saving}>
          <legend class="small muted">Verdict (appends; model facts are not changed)</legend>
          {VERDICTS.map((v) => (
            <label key={v}>
              <input type="radio" name={`verdict-${event.id}`} checked={verdict === v} onChange={() => setVerdict(v)} />
              <span>{v}</span>
            </label>
          ))}
        </fieldset>
        <label class="field">
          <span>Note (optional)</span>
          <textarea
            rows={2}
            maxLength={2000}
            value={note}
            disabled={saving}
            onInput={(e) => setNote((e.currentTarget as HTMLTextAreaElement).value)}
          />
        </label>
        {saveError && (
          <p class="alert alert-error small" role="alert">
            {saveError}
          </p>
        )}
        <button class="btn btn-primary btn-sm" type="submit" disabled={saving || !verdict}>
          {saving ? "Saving…" : "Add review"}
        </button>
      </form>
    </article>
  );
}
