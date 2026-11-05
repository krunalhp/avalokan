import pytest
from pydantic import ValidationError

from avalokan.activities import REGISTRY, Activities, Presence, Track, Tracker
from avalokan.contracts import AnalysisConfig, EventCandidate


def observation(time, x=0.4, identity=7):
    return Track(identity, "person", 0.8, (x - 0.1, 0.2, x + 0.1, 0.6), time)


def test_dwell_boundary_and_empty_observation_gap():
    config = AnalysisConfig(allowed_activities=["zone.dwell"], dwell_seconds=2)
    for end, expected in [(1.5, 0), (2.0, 1)]:
        pipeline = Activities(config)
        for n in range(int(end * 2) + 1):
            assert pipeline.observe(n / 2, [observation(n / 2)]) == []
        result = pipeline.close()
        assert len(result) == expected
        if expected:
            assert (result[0].start_s, result[0].end_s) == (0, 2)
    pipeline = Activities(config)
    pipeline.observe(0, [observation(0)])
    pipeline.observe(0.5, [observation(0.5)])
    pipeline.observe(1, [])
    pipeline.observe(20, [observation(20)])
    pipeline.observe(20.5, [observation(20.5)])
    assert pipeline.close() == []


def test_crossing_deadband_reverse_and_unknown_gap():
    pipeline = Activities(AnalysisConfig(allowed_activities=["line.crossed"]))
    events = []
    for t, x in [(0, 0.4), (0.5, 0.495), (1, 0.505), (1.5, 0.6), (2, 0.49), (2.5, 0.4), (10, 0.6)]:
        events += pipeline.observe(t, [observation(t, x)])
    assert [(e.start_s, e.attributes["direction"]) for e in events] == [
        (1.5, "left_to_right"),
        (2.5, "right_to_left"),
    ]
    assert all(e.end_s == e.start_s for e in events)


def test_tracker_uses_seconds_and_does_not_bridge_empty_detection():
    tracker = Tracker(max_gap=0.75)
    detections = [("person", 0.8, (0.2, 0.2, 0.6, 0.6))]
    first = tracker.update(3, detections)[0].id
    assert tracker.update(3.5, detections)[0].id == first
    assert tracker.update(5, detections)[0].id != first
    previous = tracker.update(5.5, detections)[0].id
    assert tracker.update(6, []) == []
    assert tracker.update(6.5, detections)[0].id != previous


def test_plugins_share_observations_and_enforce_allowlist(monkeypatch):
    config = AnalysisConfig(allowed_activities=["object.present", "zone.dwell"], dwell_seconds=1)
    pipeline = Activities(config)
    for t in [0, 0.5, 1, 1.5]:
        pipeline.observe(t, [observation(t)])
    assert {e.activity for e in pipeline.close()} == {"object.present", "zone.dwell"}
    assert Activities(AnalysisConfig(allowed_activities=[])).observe(1, [observation(1)]) == []

    class CustomPresence(Presence):
        id = "test.custom-presence"

    monkeypatch.setitem(REGISTRY, CustomPresence.id, CustomPresence)
    custom = Activities(AnalysisConfig(allowed_activities=[CustomPresence.id]))
    custom.observe(0, [observation(0)])
    custom.observe(0.5, [observation(0.5)])
    assert [(e.activity, e.start_s, e.end_s) for e in custom.close()] == [
        (CustomPresence.id, 0, 0.5)
    ]

    class Invalid(Presence):
        id = "test.invalid"

        def observe(self, time, tracks):
            return [
                EventCandidate(
                    activity="not.allowed",
                    object_class="person",
                    track_id=1,
                    start_s=0,
                    end_s=1,
                    confidence=0.7,
                    summary="invalid",
                )
            ]

    monkeypatch.setitem(REGISTRY, Invalid.id, Invalid)
    with pytest.raises(ValueError, match="allowlist"):
        Activities(AnalysisConfig(allowed_activities=[Invalid.id])).observe(1, [])


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"allowed_activities": ["typo"]},
        {"allowed_activities": [], "zone": [0.8, 0.2, 0.3, 0.9]},
        {"allowed_activities": [], "confidence": float("nan")},
        {"allowed_activities": [], "extra_option": True},
    ],
)
def test_config_rejects_missing_or_ambiguous_contract(config):
    with pytest.raises(ValidationError):
        AnalysisConfig.model_validate(config)
