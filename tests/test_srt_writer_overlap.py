"""Regression tests for SRT writer overlap prevention."""

from __future__ import annotations

from config import Config
from asr import Segment
from srt_writer import SRTWriter, write_srt_file
from subtitle_qc import run_qc


def test_prepare_segments_shrinks_previous_cue_to_min_gap():
    cfg = Config()
    writer = SRTWriter(cfg)
    segments = [
        Segment(0.0, 2.0, "", text_en_final="First cue."),
        Segment(1.8, 3.0, "", text_en_final="Second cue."),
    ]

    prepared = writer.prepare_segments(segments)

    assert prepared[0].end <= prepared[1].start - writer.min_gap


def test_written_srt_has_no_overlap_after_min_duration_extension(tmp_path):
    cfg = Config()
    cfg._config.setdefault("subtitles", {})
    cfg._config["subtitles"]["min_gap_sec"] = 0.05
    segments = [
        Segment(0.0, 0.1, "", text_en_final="First cue."),
        Segment(0.4, 1.0, "", text_en_final="Second cue."),
    ]
    out = tmp_path / "out.srt"

    write_srt_file(segments, str(out), cfg)
    qc = run_qc(out, min_duration=0.1)

    assert not any(v["type"] == "overlap" for v in qc["violations"])


# ---------------------------------------------------------------------------
# Regression tests: overlap repair must never produce cues < min_duration
# ---------------------------------------------------------------------------

def test_overlap_repair_never_shrinks_cue_below_min_duration():
    """When overlap repair shrinks a cue, the result must still be >= min_duration."""
    cfg = Config()
    writer = SRTWriter(cfg)
    min_dur = writer.min_duration
    # Second cue starts inside the first cue's min-duration window, forcing
    # overlap repair to decide between shrinking the first or shifting the second.
    segments = [
        Segment(0.0, min_dur, "", text_en_final="First cue."),
        Segment(min_dur - 0.1, min_dur * 2, "", text_en_final="Second cue."),
    ]

    prepared = writer.prepare_segments(segments)

    for seg in prepared:
        assert seg.duration >= min_dur, (
            f"Segment has duration {seg.duration:.3f}s < min_duration {min_dur}s"
        )


def test_final_srt_zero_duration_too_short_errors(tmp_path):
    """Final written SRT must have zero duration_too_short QC errors."""
    cfg = Config()
    min_dur = cfg.subtitle_min_duration
    # Tightly packed segments that force overlap repair and could shrink cues.
    segments = [
        Segment(0.0, min_dur, "", text_en_final="First."),
        Segment(min_dur * 0.8, min_dur * 2, "", text_en_final="Second."),
        Segment(min_dur * 1.6, min_dur * 3, "", text_en_final="Third."),
    ]
    out = tmp_path / "test.srt"

    write_srt_file(segments, str(out), cfg)
    qc = run_qc(out, min_duration=min_dur)

    assert not any(v["type"] == "duration_too_short" for v in qc["violations"])


def test_impossible_short_cue_dropped_not_emitted(tmp_path):
    """A cue that cannot satisfy min_duration after overlap repair is dropped."""
    cfg = Config()
    # 'Impossible' cue sits entirely inside a long cue; after overlap repair
    # it cannot be shifted to have >= min_duration without creating a new
    # overlap. It must be dropped rather than emitted as a short cue.
    segments = [
        Segment(0.0, 1.0, "", text_en_final="Long cue."),
        Segment(0.01, 0.02, "", text_en_final="Impossible."),
        Segment(2.0, 3.0, "", text_en_final="Later cue."),
    ]
    out = tmp_path / "test.srt"

    write_srt_file(segments, str(out), cfg)
    qc = run_qc(out)

    assert not any(v["type"] == "duration_too_short" for v in qc["violations"])


def test_009s_151s_431s_cues_never_emitted(tmp_path):
    """Reproduce the exact durations from the issue: 0.009s, 0.151s, 0.431s."""
    cfg = Config()
    min_dur = cfg.subtitle_min_duration  # 0.5s
    # Construct segments that would previously generate these short cues.
    segments = [
        Segment(0.000, 0.500, "", text_en_final="Cue A."),
        Segment(0.491, 1.000, "", text_en_final="Cue B (9ms overlap)."),
        Segment(0.900, 1.331, "", text_en_final="Cue C (151ms window)."),
        Segment(1.200, 1.631, "", text_en_final="Cue D (431ms window)."),
    ]
    out = tmp_path / "issue.srt"

    write_srt_file(segments, str(out), cfg)
    qc = run_qc(out, min_duration=min_dur)

    assert not any(v["type"] == "duration_too_short" for v in qc["violations"])
