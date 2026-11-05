import { useEffect, useRef, useState } from "preact/hooks";
import {
  api,
  errorText,
  isAbort,
  newIdempotencyKey,
  type Capabilities,
  type Job,
  type JobConfig,
  type Media,
  type Zone,
} from "../api";
import { fmtBytes, fmtPct, fmtTime } from "../format";
import { GeometryPreview } from "./Geometry";

const DEFAULT_CLASSES = ["person", "car", "motorcycle", "bus", "truck", "bicycle"];
const DEFAULT_ACTIVITY = "object.present";
const EXTENSIONS = [".mp4", ".mov", ".mkv"];
const ACCEPT = ".mp4,.mov,.mkv,video/mp4,video/quicktime,video/x-matroska";

type Phase = { kind: "idle" } | { kind: "uploading"; progress: number } | { kind: "starting" };

interface Props {
  caps: Capabilities;
  /** Currently selected job, offered as "re-analyze this clip". */
  selectedJob: Job | null;
  onJobCreated: (job: Job) => void;
}

function NumField(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  hint?: string;
}) {
  return (
    <label class="field field-num">
      <span>{props.label}</span>
      <input
        type="number"
        inputMode="decimal"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onInput={(e) => props.onChange(parseFloat((e.currentTarget as HTMLInputElement).value))}
      />
      {props.hint && <small class="muted">{props.hint}</small>}
    </label>
  );
}

const inRange = (v: number, lo: number, hi: number) => Number.isFinite(v) && v >= lo && v <= hi;

export function UploadForm({ caps, selectedJob, onJobCreated }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<"file" | "selected">("file");
  const [activities, setActivities] = useState<string[]>(() =>
    caps.activities.some((a) => a.id === DEFAULT_ACTIVITY) ? [DEFAULT_ACTIVITY] : [],
  );
  const [classes, setClasses] = useState<string[]>(() => {
    const d = DEFAULT_CLASSES.filter((c) => caps.classes.includes(c));
    return d.length ? d : [...caps.classes];
  });
  const [sampleFps, setSampleFps] = useState<1 | 2 | 5>(2);
  const [confidence, setConfidence] = useState(0.3);
  const [dwell, setDwell] = useState(10);
  const [lineX, setLineX] = useState(0.5);
  const [zone, setZone] = useState<Zone>([0.2, 0.2, 0.8, 0.9]);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fileInput = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  /** Media already uploaded for the chosen File, so a failed job start can be retried without re-uploading. */
  const uploadedRef = useRef<{ file: File; media: Media } | null>(null);
  /** Same key is reused when retrying an identical (media, config) submission. */
  const idemRef = useRef<{ sig: string; key: string } | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => {
    if (!selectedJob && source === "selected") setSource("file");
  }, [selectedJob, source]);

  const busy = phase.kind !== "idle";

  function buildConfig(): JobConfig {
    return {
      allowed_activities: activities,
      classes,
      sample_fps: sampleFps,
      confidence,
      dwell_seconds: dwell,
      line_x: lineX,
      zone,
    };
  }

  function validate(): string[] {
    const errs: string[] = [];
    if (source === "file") {
      if (!file) errs.push("Choose a video file.");
      else {
        const lower = file.name.toLowerCase();
        if (!EXTENSIONS.some((x) => lower.endsWith(x))) errs.push("File must be MP4, MOV or MKV.");
        if (caps.max_upload_bytes && file.size > caps.max_upload_bytes)
          errs.push(`File is ${fmtBytes(file.size)}; limit is ${fmtBytes(caps.max_upload_bytes)}.`);
      }
    }
    if (!classes.length) errs.push("Select at least one object class.");
    if (!inRange(confidence, 0.1, 0.9)) errs.push("Confidence threshold must be 0.1–0.9.");
    if (!inRange(dwell, 1, 600)) errs.push("Dwell must be 1–600 seconds.");
    if (!inRange(lineX, 0.05, 0.95)) errs.push("Line x must be 0.05–0.95.");
    const [x1, y1, x2, y2] = zone;
    if (![x1, y1, x2, y2].every((v) => inRange(v, 0, 1)) || !(x2 > x1 && y2 > y1))
      errs.push("Zone must be normalized (0–1) with x2 > x1 and y2 > y1.");
    return errs;
  }

  async function submit(e: Event) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    const errs = validate();
    if (errs.length) {
      setError(errs.join(" "));
      return;
    }
    const config = buildConfig();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      let mediaId: string;
      if (source === "selected" && selectedJob) {
        mediaId = selectedJob.media_id;
      } else {
        const f = file!;
        if (uploadedRef.current?.file === f) {
          mediaId = uploadedRef.current.media.id;
        } else {
          setPhase({ kind: "uploading", progress: 0 });
          const media = await api.uploadMedia(f, (p) => setPhase({ kind: "uploading", progress: p }), ctrl.signal);
          uploadedRef.current = { file: f, media };
          mediaId = media.id;
        }
      }
      setPhase({ kind: "starting" });
      const sig = `${mediaId}|${JSON.stringify(config)}`;
      if (idemRef.current?.sig !== sig) idemRef.current = { sig, key: newIdempotencyKey() };
      const job = await api.createJob(mediaId, config, idemRef.current.key);
      idemRef.current = null;
      if (source === "file") {
        uploadedRef.current = null;
        setFile(null);
        if (fileInput.current) fileInput.current.value = "";
      }
      setNotice(
        config.allowed_activities.length
          ? "Analysis job created. Its current status appears beside the video."
          : "Job created with no activities: it will emit no semantic events.",
      );
      onJobCreated(job);
    } catch (err) {
      if (isAbort(err)) setNotice("Upload cancelled.");
      else
        setError(
          errorText(err) +
            (uploadedRef.current && source === "file" ? " The clip is uploaded; submit again to retry." : ""),
        );
    } finally {
      abortRef.current = null;
      setPhase({ kind: "idle" });
    }
  }

  const toggle = (list: string[], v: string, on: boolean) => (on ? [...new Set([...list, v])] : list.filter((x) => x !== v));

  return (
    <form class="panel-section upload" onSubmit={submit} aria-labelledby="upload-title" noValidate>
      <h2 id="upload-title" class="section-title">
        New analysis
      </h2>

      {selectedJob && (
        <fieldset class="segmented" disabled={busy}>
          <legend class="sr-only">Clip source</legend>
          <label>
            <input type="radio" name="source" checked={source === "file"} onChange={() => setSource("file")} />
            <span>Upload file</span>
          </label>
          <label title={selectedJob.media_name}>
            <input type="radio" name="source" checked={source === "selected"} onChange={() => setSource("selected")} />
            <span>Re-analyze selected</span>
          </label>
        </fieldset>
      )}

      {source === "file" ? (
        <label class="dropzone">
          <span class="dropzone-title">{file ? file.name : "Choose CCTV clip"}</span>
          <small class="muted">
            {file
              ? fmtBytes(file.size)
              : `MP4, MOV or MKV · up to ${fmtBytes(caps.max_upload_bytes)} · ${fmtTime(caps.max_duration_s)} max`}
          </small>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            disabled={busy}
            aria-label="Video file (MP4, MOV or MKV)"
            onChange={(e) => {
              const f = (e.currentTarget as HTMLInputElement).files?.[0] ?? null;
              setFile(f);
              setError(null);
            }}
          />
        </label>
      ) : (
        <p class="muted small">
          New job on <strong class="ellipsis">{selectedJob?.media_name}</strong> (existing upload).
        </p>
      )}

      <fieldset class="group" disabled={busy}>
        <legend>Activities</legend>
        {caps.activities.length === 0 && <p class="muted small">This server offers no activities.</p>}
        {caps.activities.map((a) => (
          <label class="check" key={a.id}>
            <input
              type="checkbox"
              checked={activities.includes(a.id)}
              onChange={(e) => setActivities(toggle(activities, a.id, (e.currentTarget as HTMLInputElement).checked))}
            />
            <span>
              <span class="check-name">{a.name || a.id}</span>
              {a.status && a.status !== "stable" && <span class="badge badge-warn">{a.status}</span>}
              <small class="muted block">{a.description}</small>
            </span>
          </label>
        ))}
        {activities.length === 0 && caps.activities.length > 0 && (
          <p class="hint-warn small">No activities selected: the job is deny-all and emits no events.</p>
        )}
      </fieldset>

      <details class="group">
        <summary>Classes &amp; sampling</summary>
        <fieldset class="chips" disabled={busy}>
          <legend class="sr-only">Object classes</legend>
          {caps.classes.map((c) => (
            <label class="chip" key={c}>
              <input
                type="checkbox"
                checked={classes.includes(c)}
                onChange={(e) => setClasses(toggle(classes, c, (e.currentTarget as HTMLInputElement).checked))}
              />
              <span>{c}</span>
            </label>
          ))}
        </fieldset>
        <div class="grid-2">
          <label class="field">
            <span>Sample rate</span>
            <select
              value={sampleFps}
              disabled={busy}
              onChange={(e) => setSampleFps(Number((e.currentTarget as HTMLSelectElement).value) as 1 | 2 | 5)}
            >
              <option value={1}>1 fps</option>
              <option value={2}>2 fps</option>
              <option value={5}>5 fps</option>
            </select>
          </label>
          <NumField label="Min. detector score" value={confidence} min={0.1} max={0.9} step={0.05} onChange={setConfidence} />
        </div>
        <p class="muted small">Low sample rates can miss short events; skipped frames are still decoded.</p>
      </details>

      <details class="group">
        <summary>Line &amp; zone geometry</summary>
        <p class="muted small">Normalized 0–1 frame coordinates, used by line-crossing and zone-dwell activities.</p>
        <div class="grid-2">
          <NumField label="Line x" value={lineX} min={0.05} max={0.95} step={0.01} onChange={setLineX} />
          <NumField label="Dwell (s)" value={dwell} min={1} max={600} step={1} onChange={setDwell} />
          {(["Zone x1", "Zone y1", "Zone x2", "Zone y2"] as const).map((label, i) => (
            <NumField
              key={label}
              label={label}
              value={zone[i]}
              min={0}
              max={1}
              step={0.01}
              onChange={(v) => {
                const z = [...zone] as Zone;
                z[i] = v;
                setZone(z);
              }}
            />
          ))}
        </div>
        <GeometryPreview lineX={lineX} zone={zone} />
      </details>

      {phase.kind === "uploading" && (
        <div class="progress-block" aria-live="polite">
          <div class="row between small">
            <span>Uploading…</span>
            <span>{fmtPct(phase.progress)}</span>
          </div>
          <progress max={1} value={phase.progress} aria-label="Upload progress" />
        </div>
      )}
      {error && (
        <p class="alert alert-error" role="alert">
          {error}
        </p>
      )}
      {notice && !error && (
        <p class="alert alert-ok" role="status">
          {notice}
        </p>
      )}

      <div class="row">
        <button class="btn btn-primary grow" type="submit" disabled={busy}>
          {phase.kind === "uploading" ? "Uploading…" : phase.kind === "starting" ? "Starting job…" : source === "selected" ? "Analyze selected clip" : "Upload & analyze"}
        </button>
        {phase.kind === "uploading" && (
          <button class="btn" type="button" onClick={() => abortRef.current?.abort()}>
            Cancel
          </button>
        )}
      </div>
      {!caps.model.ready && <p class="hint-warn small">The detector model is not ready on the server.</p>}
    </form>
  );
}
