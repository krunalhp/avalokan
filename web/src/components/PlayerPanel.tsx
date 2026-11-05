import type { RefObject } from "preact";
import { useEffect, useState } from "preact/hooks";
import { api, errorText, isAbort, type AnalysisEvent, type Job, type Media } from "../api";
import { fmtBytes, fmtDate, fmtPct, fmtTime, fmtValue, humanize, shortHash } from "../format";
import { GeometryOverlay } from "./Geometry";
import { StatusBadge } from "./JobList";

const MEDIA_POLL_MS = 3000;
const MEDIA_POLL_MAX = 100; // ~5 minutes of waiting for a playback proxy

/** Load media metadata; while the playback proxy is not ready, poll a bounded number of times. */
function useMedia(mediaId: string | null, retryTick: number) {
  const [media, setMedia] = useState<Media | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gaveUp, setGaveUp] = useState(false);

  useEffect(() => {
    setMedia(null);
    setError(null);
    setGaveUp(false);
    if (!mediaId) return;
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    const run = async () => {
      try {
        const m = await api.media(mediaId, ctrl.signal);
        setMedia(m);
        setError(null);
        if (m.playback_ready === false) {
          if (++attempts >= MEDIA_POLL_MAX) setGaveUp(true);
          else timer = setTimeout(run, MEDIA_POLL_MS);
        }
      } catch (e) {
        if (!isAbort(e)) setError(errorText(e));
      }
    };
    run();
    return () => {
      ctrl.abort();
      clearTimeout(timer);
    };
  }, [mediaId, retryTick]);

  return { media, error, gaveUp };
}

interface Props {
  job: Job | null;
  videoRef: RefObject<HTMLVideoElement>;
  events: AnalysisEvent[];
  selectedEventId: string | null;
  currentTime: number;
  onSelectEvent: (e: AnalysisEvent) => void;
  onTimeUpdate: (t: number) => void;
}

export function PlayerPanel({ job, videoRef, events, selectedEventId, currentTime, onSelectEvent, onTimeUpdate }: Props) {
  const [retryTick, setRetryTick] = useState(0);
  const { media, error, gaveUp } = useMedia(job?.media_id ?? null, retryTick);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [showGeometry, setShowGeometry] = useState(false);
  const [videoDuration, setVideoDuration] = useState<number | null>(null);

  useEffect(() => {
    setVideoError(null);
    setVideoDuration(null);
  }, [job?.media_id]);

  if (!job) {
    return (
      <section class="player-empty" aria-label="Player">
        <div class="empty-state">
          <h2>No clip selected</h2>
          <p class="muted">Upload a CCTV clip or pick a job from the library to play it and review detected events.</p>
        </div>
      </section>
    );
  }

  const playable = media && media.playback_ready !== false;
  const duration = videoDuration ?? media?.duration_s ?? job.stats?.duration_s;
  const dur = typeof duration === "number" && duration > 0 ? duration : null;
  const aspect = media && media.width > 0 && media.height > 0 ? media.width / media.height : 16 / 9;

  return (
    <section class="player" aria-label="Player">
      <div class="row between player-head">
        <h2 class="clip-title ellipsis" title={job.media_name}>
          {job.media_name}
        </h2>
        <label class="check inline small">
          <input
            type="checkbox"
            checked={showGeometry}
            onChange={(e) => setShowGeometry((e.currentTarget as HTMLInputElement).checked)}
          />
          <span>Show line/zone</span>
        </label>
      </div>

      <div class="video-frame" style={{ aspectRatio: String(aspect), maxWidth: `calc(62vh * ${aspect})` }}>
        {playable && (
          <video
            ref={videoRef}
            src={api.videoUrl(media.id)}
            controls
            preload="metadata"
            playsInline
            aria-label={`Video: ${job.media_name}`}
            onTimeUpdate={(e) => onTimeUpdate((e.currentTarget as HTMLVideoElement).currentTime)}
            onSeeked={(e) => onTimeUpdate((e.currentTarget as HTMLVideoElement).currentTime)}
            onLoadedMetadata={(e) => {
              const d = (e.currentTarget as HTMLVideoElement).duration;
              if (Number.isFinite(d)) setVideoDuration(d);
              setVideoError(null);
            }}
            onError={() =>
              setVideoError(
                "The browser could not load this video. The playback proxy may be unavailable, the session may have expired, or the codec is unsupported.",
              )
            }
          />
        )}
        {showGeometry && playable && <GeometryOverlay lineX={job.config.line_x} zone={job.config.zone} />}
        {!playable && (
          <div class="video-placeholder" aria-live="polite">
            {error ? (
              <p class="alert alert-error">{error}</p>
            ) : !media ? (
              <p class="muted">Loading clip…</p>
            ) : gaveUp ? (
              <p class="muted">
                Playback proxy still not ready.{" "}
                <button class="link" type="button" onClick={() => setRetryTick((t) => t + 1)}>
                  Check again
                </button>
              </p>
            ) : (
              <p class="muted">Preparing a browser-playable copy… the original file is preserved.</p>
            )}
          </div>
        )}
      </div>

      {videoError && (
        <p class="alert alert-error small" role="alert">
          {videoError}{" "}
          <button
            class="link"
            type="button"
            onClick={() => {
              setVideoError(null);
              setRetryTick((t) => t + 1);
              videoRef.current?.load();
            }}
          >
            Retry
          </button>
        </p>
      )}

      {dur && events.length > 0 && (
        <div class="timeline" aria-hidden="true" title="Loaded events on the clip timeline">
          {events.map((ev) => (
            <button
              key={ev.id}
              type="button"
              tabIndex={-1}
              class={`tl-seg ${ev.start_s === ev.end_s ? "point" : ""} ${ev.id === selectedEventId ? "selected" : ""}`}
              style={{
                left: `${Math.min(100, (ev.start_s / dur) * 100)}%`,
                width: ev.start_s === ev.end_s ? undefined : `${Math.max(0.4, ((ev.end_s - ev.start_s) / dur) * 100)}%`,
              }}
              onClick={() => onSelectEvent(ev)}
            />
          ))}
          <span class="tl-head" style={{ left: `${Math.min(100, (currentTime / dur) * 100)}%` }} />
        </div>
      )}

      <JobStatus job={job} media={media} />
    </section>
  );
}

const STAT_KEYS = [
  "duration_s",
  "decoded_frames",
  "analyzed_frames",
  "sample_fps",
  "analysis_fps",
  "elapsed_s",
  "cpu_s",
  "playback_preparation_s",
  "time_basis",
  "tracker_version",
  "model_sha256",
];

function JobStatus({ job, media }: { job: Job; media: Media | null }) {
  const stats = job.stats ?? {};
  const keys = [...STAT_KEYS.filter((k) => k in stats), ...Object.keys(stats).filter((k) => !STAT_KEYS.includes(k))];
  return (
    <div class="job-status" aria-live="polite">
      <div class="row between">
        <span class="row gap-sm">
          <StatusBadge status={job.status} />
          <span class="small muted">
            {job.status === "queued" && "Waiting for a worker…"}
            {job.status === "running" && `Analyzing · ${fmtPct(job.progress)}`}
            {job.status === "completed" && `${job.event_count} events · finished ${fmtDate(job.finished_at)}`}
            {job.status === "failed" && `Failed ${fmtDate(job.finished_at)} · no partial results published`}
          </span>
        </span>
        {media && (
          <span class="small muted">
            {media.width}×{media.height} · {media.codec} · {fmtTime(media.duration_s)} · {fmtBytes(media.size_bytes)}
          </span>
        )}
      </div>
      {(job.status === "queued" || job.status === "running") && (
        <progress max={1} value={job.status === "queued" ? 0 : job.progress} aria-label="Analysis progress" />
      )}
      {job.status === "failed" && job.error && (
        <p class="alert alert-error small" role="alert">
          {job.error}
        </p>
      )}
      {keys.length > 0 && (
        <details class="stats">
          <summary class="small">Run statistics &amp; configuration</summary>
          <dl class="kv">
            {keys.map((k) => (
              <div key={k}>
                <dt>{humanize(k)}</dt>
                <dd>{k.includes("sha256") ? <code title={String(stats[k])}>{shortHash(stats[k])}</code> : fmtValue(stats[k])}</dd>
              </div>
            ))}
            <div>
              <dt>Config</dt>
              <dd>
                <code class="wrap">{JSON.stringify(job.config)}</code>
              </dd>
            </div>
          </dl>
          <p class="muted small">Wall/CPU cost is a measurement of this run, not an accuracy claim.</p>
        </details>
      )}
    </div>
  );
}
