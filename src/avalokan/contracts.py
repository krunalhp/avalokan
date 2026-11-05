from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

CLASSES = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


class AnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    allowed_activities: list[str]
    classes: list[str] = Field(default_factory=lambda: list(CLASSES.values()), min_length=1)
    sample_fps: Literal[1, 2, 5] = 2
    confidence: float = Field(default=0.3, ge=0.1, le=0.9)
    dwell_seconds: float = Field(default=10, ge=1, le=600)
    line_x: float = Field(default=0.5, ge=0.05, le=0.95)
    zone: tuple[float, float, float, float] = (0.2, 0.2, 0.8, 0.9)

    @model_validator(mode="after")
    def validate_values(self):
        from .activities import REGISTRY

        if len(set(self.allowed_activities)) != len(self.allowed_activities):
            raise ValueError("Duplicate activities")
        if set(self.allowed_activities) - REGISTRY.keys():
            raise ValueError("Unsupported activity")
        if set(self.classes) - set(CLASSES.values()) or len(set(self.classes)) != len(self.classes):
            raise ValueError("Unsupported or duplicate object class")
        x1, y1, x2, y2 = self.zone
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("Zone must be a normalized positive-area rectangle")
        return self


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    media_id: UUID
    config: AnalysisConfig


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["confirmed", "rejected", "uncertain"]
    note: str = Field(default="", max_length=2000)


class SessionRequest(BaseModel):
    token: str = Field(min_length=1, max_length=1000)


class EventCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    activity: str
    object_class: str
    track_id: int
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    summary: str
    confidence: float = Field(ge=0, le=1)
    attributes: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_s < self.start_s:
            raise ValueError("Event ends before it starts")
        return self


class MediaRecord(BaseModel):
    id: UUID
    name: str
    duration_s: float
    width: int
    height: int
    codec: str
    size_bytes: int
    sha256: str
    playback_ready: bool
    created_at: datetime


class JobRecord(BaseModel):
    id: UUID
    media_id: UUID
    media_name: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: float
    config: dict
    error: str | None
    stats: dict
    created_at: datetime
    finished_at: datetime | None
    event_count: int


class ReviewRecord(ReviewRequest):
    id: UUID
    created_at: datetime


class EventRecord(BaseModel):
    id: UUID
    job_id: UUID
    activity: str
    object_class: str
    track_id: int
    start_s: float
    end_s: float
    summary: str
    confidence: float
    attributes: dict
    provenance: dict
    review_status: Literal["unreviewed", "confirmed", "rejected", "uncertain"]


class EventDetail(EventRecord):
    reviews: list[ReviewRecord]


class MetricSample(BaseModel):
    time_s: float
    counts: dict[str, int]


Item = TypeVar("Item")


class Page(BaseModel, Generic[Item]):
    items: list[Item]
    next_cursor: str | None


class JobList(BaseModel):
    items: list[JobRecord]
