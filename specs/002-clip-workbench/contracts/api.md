# Workbench API v1 contract

Same-origin `/v1`; JSON except multipart upload and video. All endpoints except
`/health` require `Authorization: Bearer …` or an authenticated HttpOnly cookie.
`POST /v1/session` accepts `{token}` and sets that cookie; DELETE clears it.
Explicit `AVALOKAN_DEMO=1` disables auth for a trusted local/orb demo; capabilities
and UI must disclose this. Never place tokens in URLs. OpenAPI at `/openapi.json`.
Errors use `{detail: string | validation_errors}`. Files never reveal server paths.

- `GET /v1/capabilities` → `{activities:[{id,name,description,status}], classes:[string], config_schema:object, model:{name,sha256,ready}, access_mode, max_upload_bytes, max_duration_s}`.
- `POST /v1/media` multipart field `file` → 201 `{id,name,duration_s,width,height,codec,size_bytes,sha256}`. Validate actual media, not MIME alone. 413 oversized, 422 invalid/unsupported.
- `GET /v1/media/{id}` → same metadata plus `playback_ready:boolean`.
- `GET /v1/media/{id}/video` → authenticated range-supporting MP4; 409 while proxy unavailable.
- `POST /v1/jobs` JSON `{media_id,config}`, mandatory `Idempotency-Key` header → 202 job. Same key+payload returns same job; changed payload 409; queue full 429.
- `GET /v1/jobs?limit=50` → `{items:[job]}` newest first, max100.
- `GET /v1/jobs/{id}` → job.
- `GET /v1/events?job_id=…&activity=…&object_class=…&from_s=…&to_s=…&cursor=…&limit=100` → `{items:[event],next_cursor:string|null}`. job_id required. Immutable sequence cursor, limit1–500, half-open overlap for intervals and `[from,to)` points. Times are relative seconds; no UTC anchor assumed.
- `GET /v1/events/{id}` → event plus `reviews:[{id,verdict,note,created_at}]`.
- `POST /v1/events/{id}/reviews` JSON `{verdict:"confirmed"|"rejected"|"uncertain",note:string}` → 201 review. Append only; does not rewrite model facts.
- `GET /v1/jobs/{id}/metrics?cursor=…&limit=100` → `{items:[{time_s,counts:{class:integer}}],next_cursor}`. Sampled occupancy gauge, not sum/count of unique people; unknown between observations.

`config` (extra keys rejected):
```
{"allowed_activities":["object.present"],"classes":["person","car","motorcycle","bus","truck","bicycle"],"sample_fps":2,"confidence":0.3,"dwell_seconds":10,"line_x":0.5,"zone":[0.2,0.2,0.8,0.9]}
```
All fields except allowed_activities have those defaults. Empty allowlist is
valid deny-all. sample_fps is 1,2,5; confidence .1–.9; dwell 1–600 seconds;
line_x .05–.95; zone normalized positive-area rectangle. Instance allowlist from
environment can further restrict requested activities; unsupported IDs fail.

`job`: `{id,media_id,media_name,status:"queued"|"running"|"completed"|"failed",progress:0..1,config,error:null|string,stats:object,created_at,finished_at:null|string,event_count:integer}`.
Stats on completion include decoded_frames, analyzed_frames, elapsed_s,
cpu_s, duration_s, analysis_fps, model_sha256, tracker_version, time_basis,
sample_fps, playback_preparation_s. Progress excludes unknown work; completed=1.

`event`: `{id,job_id,activity,object_class,track_id,start_s,end_s,summary,confidence,attributes:object,provenance:object,review_status:"unreviewed"|"confirmed"|"rejected"|"uncertain"}`.
Presence/dwell are observed intervals; crossing is a point (equal start/end).
Confidence is model support, not calibrated probability. IDs are run-scoped;
re-analysis is a distinct result set, never silently mixed into counts.
