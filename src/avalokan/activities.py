"""Trusted activity registry and conservative source-time IoU baseline.

Plugins own rule state, not media, inference sessions or database connections.
This baseline intentionally breaks continuity on a missed detection; it cannot
claim identity through occlusion. Replace Tracker after labeled evaluation.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from .contracts import EventCandidate

TRACKER_VERSION = "iou-consecutive-v1"


@dataclass
class Track:
    id: int
    object_class: str
    score: float
    box: tuple
    time: float

    @property
    def anchor(self):
        return ((self.box[0] + self.box[2]) / 2, self.box[3])


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union else 0


class Tracker:
    def __init__(self, max_gap):
        self.max_gap = max_gap
        self.previous = []
        self.next_id = 1

    def update(self, time, detections):
        previous = [t for t in self.previous if 0 < time - t.time <= self.max_gap]
        assigned = {}
        if previous and detections:
            costs = np.array(
                [
                    [1 - iou(t.box, d[2]) if t.object_class == d[0] else 2 for d in detections]
                    for t in previous
                ]
            )
            rows, cols = linear_sum_assignment(costs)
            assigned = {j: previous[i].id for i, j in zip(rows, cols) if costs[i, j] <= 0.85}
        current = []
        for j, (name, score, box) in enumerate(detections):
            identity = assigned.get(j)
            if identity is None:
                identity = self.next_id
                self.next_id += 1
            current.append(Track(identity, name, score, box, time))
        self.previous = current
        return current


class Presence:
    id = "object.present"
    name = "Object presence"
    description = "Consecutive sampled observations of a person or vehicle. Not identity."

    def __init__(self, config):
        self.config = config
        self.states = {}

    def eligible(self, track):
        return True

    def finish(self, state, reason):
        first, last, count, minimum = state
        if count < 2:
            return []
        duration = last.time - first.time
        return [
            EventCandidate(
                activity=self.id,
                object_class=last.object_class,
                track_id=last.id,
                start_s=first.time,
                end_s=last.time,
                confidence=minimum,
                summary=f"{last.object_class.capitalize()} observed from {first.time:.2f}s to {last.time:.2f}s.",
                attributes={
                    "confirmation_count": count,
                    "supported_span_s": duration,
                    "closure_reason": reason,
                    "anchor": "bottom_center",
                },
            )
        ]

    def observe(self, time, tracks):
        eligible = {t.id: t for t in tracks if self.eligible(t)}
        events = []
        for identity in list(self.states):
            state = self.states[identity]
            if identity not in eligible or time - state[1].time > 1.5 / self.config.sample_fps:
                events += self.finish(self.states.pop(identity), "observation_lost")
        for identity, track in eligible.items():
            if identity in self.states:
                first, _, count, minimum = self.states[identity]
                self.states[identity] = (first, track, count + 1, min(minimum, track.score))
            else:
                self.states[identity] = (track, track, 1, track.score)
        return events

    def close(self):
        events = [e for state in self.states.values() for e in self.finish(state, "analysis_end")]
        self.states.clear()
        return events


class Dwell(Presence):
    id = "zone.dwell"
    name = "Zone dwell"
    description = "Sustained sampled presence inside a configured rectangle."

    def eligible(self, track):
        x, y = track.anchor
        x1, y1, x2, y2 = self.config.zone
        return x1 <= x <= x2 and y1 <= y <= y2

    def finish(self, state, reason):
        first, last, _, _ = state
        if last.time - first.time < self.config.dwell_seconds:
            return []
        events = super().finish(state, reason)
        for event in events:
            event.summary = f"{last.object_class.capitalize()} remained in the configured zone for {last.time - first.time:.2f} supported seconds."
            event.attributes.update(zone=self.config.zone, threshold_s=self.config.dwell_seconds)
        return events


class Crossing:
    id = "line.crossed"
    name = "Line crossing"
    description = "Confirmed movement across a vertical line with a 2% deadband."

    def __init__(self, config):
        self.config = config
        self.states = {}

    def observe(self, time, tracks):
        events, current = [], {}
        for track in tracks:
            delta = track.anchor[0] - self.config.line_x
            side = 1 if delta > 0.02 else -1 if delta < -0.02 else 0
            previous = self.states.get(track.id)
            if previous and time - previous[1] > 1.5 / self.config.sample_fps:
                previous = None
            if side and previous and previous[0] and side != previous[0]:
                direction = "left_to_right" if side == 1 else "right_to_left"
                events.append(
                    EventCandidate(
                        activity=self.id,
                        object_class=track.object_class,
                        track_id=track.id,
                        start_s=time,
                        end_s=time,
                        confidence=track.score,
                        summary=f"{track.object_class.capitalize()} crossed the line {direction.replace('_', ' ')} at {time:.2f}s.",
                        attributes={
                            "direction": direction,
                            "line_x": self.config.line_x,
                            "boundary_uncertainty_s": time - previous[2],
                        },
                    )
                )
            # Keep side through the deadband, but time of the last observation
            # separately from the time of the last confirmed side.
            current[track.id] = (
                side or (previous[0] if previous else 0),
                time,
                time if side else previous[2] if previous else time,
            )
        self.states = current
        return events

    def close(self):
        self.states.clear()
        return []


REGISTRY = {plugin.id: plugin for plugin in (Presence, Crossing, Dwell)}


class Activities:
    def __init__(self, config):
        self.allowed = set(config.allowed_activities)
        self.plugins = [REGISTRY[name](config) for name in config.allowed_activities]

    def _checked(self, plugin, candidates):
        for candidate in candidates:
            event = EventCandidate.model_validate(candidate)
            if event.activity != plugin.id or event.activity not in self.allowed:
                raise ValueError("Plugin violated its activity allowlist")
            yield event

    def observe(self, time, tracks):
        return [e for p in self.plugins for e in self._checked(p, p.observe(time, tracks))]

    def close(self):
        return [e for p in self.plugins for e in self._checked(p, p.close())]
