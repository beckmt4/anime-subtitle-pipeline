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
