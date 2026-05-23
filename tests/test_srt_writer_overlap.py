"""Regression tests for SRT writer overlap prevention."""

from __future__ import annotations

from config import Config
from models import Segment, SubtitleCandidate
from srt_writer import write_candidate_srt
from subtitle_qc import run_qc


def _candidate(segments: list[Segment]) -> SubtitleCandidate:
    return SubtitleCandidate(
        id="test_candidate",
        language="en",
        source="mt",
        origin_stream="audio:0",
        segments=segments,
        meta={},
    )


def test_written_srt_repairs_overlapping_cues(tmp_path):
    cfg = Config()
    segments = [
        Segment(0.0, 2.0, "First cue."),
        Segment(1.8, 3.0, "Second cue."),
    ]
    out = tmp_path / "overlap.srt"

    write_candidate_srt(_candidate(segments), str(out), cfg)
    qc = run_qc(out, min_duration=cfg.subtitle_min_duration)

    assert not any(v["type"] == "overlap" for v in qc["violations"])


def test_written_srt_has_no_overlap_after_min_duration_extension(tmp_path):
    cfg = Config()
    cfg._config.setdefault("subtitles", {})
    cfg._config["subtitles"]["min_gap_sec"] = 0.05
    segments = [
        Segment(0.0, 0.1, "First cue."),
        Segment(0.4, 1.0, "Second cue."),
    ]
    out = tmp_path / "out.srt"

    write_candidate_srt(_candidate(segments), str(out), cfg)
    qc = run_qc(out, min_duration=0.1)

    assert not any(v["type"] == "overlap" for v in qc["violations"])


# ---------------------------------------------------------------------------
# Regression tests: overlap repair must never produce cues < min_duration
# ---------------------------------------------------------------------------

def test_overlap_repair_never_shrinks_cue_below_min_duration(tmp_path):
    """When overlap repair shrinks a cue, the result must still be >= min_duration."""
    cfg = Config()
    min_dur = cfg.subtitle_min_duration
    # Second cue starts inside the first cue's min-duration window, forcing
    # overlap repair to decide between shrinking the first or shifting the second.
    segments = [
        Segment(0.0, min_dur, "First cue."),
        Segment(min_dur - 0.1, min_dur * 2, "Second cue."),
    ]
    out = tmp_path / "tmp_overlap_min_duration.srt"

    write_candidate_srt(_candidate(segments), str(out), cfg)
    qc = run_qc(out, min_duration=min_dur)

    assert not any(v["type"] == "duration_too_short" for v in qc["violations"])


def test_final_srt_zero_duration_too_short_errors(tmp_path):
    """Final written SRT must have zero duration_too_short QC errors."""
    cfg = Config()
    min_dur = cfg.subtitle_min_duration
    # Tightly packed segments that force overlap repair and could shrink cues.
    segments = [
        Segment(0.0, min_dur, "First."),
        Segment(min_dur * 0.8, min_dur * 2, "Second."),
        Segment(min_dur * 1.6, min_dur * 3, "Third."),
    ]
    out = tmp_path / "test.srt"

    write_candidate_srt(_candidate(segments), str(out), cfg)
    qc = run_qc(out, min_duration=min_dur)

    assert not any(v["type"] == "duration_too_short" for v in qc["violations"])


def test_impossible_short_cue_dropped_not_emitted(tmp_path):
    """A cue that cannot satisfy min_duration after overlap repair is dropped."""
    cfg = Config()
    # 'Impossible' cue sits entirely inside a long cue; after overlap repair
    # it cannot be shifted to have >= min_duration without creating a new
    # overlap. It must be dropped rather than emitted as a short cue.
    segments = [
        Segment(0.0, 1.0, "Long cue."),
        Segment(0.01, 0.02, "Impossible."),
        Segment(2.0, 3.0, "Later cue."),
    ]
    out = tmp_path / "test.srt"

    write_candidate_srt(_candidate(segments), str(out), cfg)
    qc = run_qc(out)

    assert not any(v["type"] == "duration_too_short" for v in qc["violations"])


def test_009s_151s_431s_cues_never_emitted(tmp_path):
    """Reproduce the exact durations from the issue: 0.009s, 0.151s, 0.431s."""
    cfg = Config()
    min_dur = cfg.subtitle_min_duration  # 0.5s
    # Construct segments that would previously generate these short cues.
    segments = [
        Segment(0.000, 0.500, "Cue A."),
        Segment(0.491, 1.000, "Cue B (9ms overlap)."),
        Segment(0.900, 1.331, "Cue C (151ms window)."),
        Segment(1.200, 1.631, "Cue D (431ms window)."),
    ]
    out = tmp_path / "issue.srt"

    write_candidate_srt(_candidate(segments), str(out), cfg)
    qc = run_qc(out, min_duration=min_dur)

    assert not any(v["type"] == "duration_too_short" for v in qc["violations"])
