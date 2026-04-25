"""Unit tests for subtitle_qc — deterministic fixture-based checks.

All tests use small inline SRT fixtures written to a tmp_path; no ML models,
ffmpeg, or external services are required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from subtitle_qc import run_qc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_srt(tmp_path: Path, content: str, name: str = "test.srt") -> Path:
    """Write *content* to *tmp_path/name* and return the path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


MINIMAL_SRT = """\
1
00:00:01,000 --> 00:00:03,000
Hello world.

2
00:00:04,000 --> 00:00:06,000
Goodbye world.
"""


# ---------------------------------------------------------------------------
# 1. Parseability
# ---------------------------------------------------------------------------


class TestParseability:
    def test_valid_file_passes(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p)
        assert result["parsed_ok"] is True
        assert result["cue_count"] == 2

    def test_missing_file_is_parse_error(self, tmp_path):
        result = run_qc(tmp_path / "nonexistent.srt")
        assert result["parsed_ok"] is False
        assert result["pass_qc"] is False
        assert any(v["type"] == "parse_failed" for v in result["violations"])

    def test_missing_file_violation_is_error_severity(self, tmp_path):
        result = run_qc(tmp_path / "nonexistent.srt")
        v = next(v for v in result["violations"] if v["type"] == "parse_failed")
        assert v["severity"] == "error"

    def test_empty_file_is_parse_error(self, tmp_path):
        p = write_srt(tmp_path, "")
        result = run_qc(p)
        assert result["parsed_ok"] is False
        assert any(v["type"] == "parse_failed" for v in result["violations"])

    def test_garbage_content_is_parse_error(self, tmp_path):
        p = write_srt(tmp_path, "this is not an SRT file\njust garbage\nno timestamps")
        result = run_qc(p)
        assert result["parsed_ok"] is False

    def test_cue_count_reflects_actual_count(self, tmp_path):
        srt = "\n\n".join(
            f"{i}\n00:00:{i:02d},000 --> 00:00:{i:02d},500\nCue {i}"
            for i in range(1, 6)
        )
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert result["cue_count"] == 5

    def test_single_cue_file_parses(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:02,000\nSingle cue.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert result["parsed_ok"] is True
        assert result["cue_count"] == 1

    def test_crlf_line_endings_accepted(self, tmp_path):
        content = MINIMAL_SRT.replace("\n", "\r\n")
        p = write_srt(tmp_path, content)
        result = run_qc(p)
        assert result["parsed_ok"] is True
        assert result["cue_count"] == 2


# ---------------------------------------------------------------------------
# 2. Cue count
# ---------------------------------------------------------------------------


class TestCueCount:
    def test_passes_when_cue_count_meets_minimum(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p, min_cues=2)
        assert not any(v["type"] == "too_few_cues" for v in result["violations"])

    def test_error_when_fewer_cues_than_minimum(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p, min_cues=10)
        violations = [v for v in result["violations"] if v["type"] == "too_few_cues"]
        assert violations
        assert violations[0]["severity"] == "error"

    def test_cue_count_file_level_index(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p, min_cues=100)
        v = next(v for v in result["violations"] if v["type"] == "too_few_cues")
        assert v["cue_index"] == -1  # file-level, not per-cue


# ---------------------------------------------------------------------------
# 3 & 4. Out-of-order and overlapping cues
# ---------------------------------------------------------------------------


class TestTimingOrder:
    def test_valid_ordering_no_timing_violation(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p)
        assert not any(
            v["type"] in ("out_of_order", "overlap") for v in result["violations"]
        )

    def test_out_of_order_detected(self, tmp_path):
        srt = """\
1
00:00:05,000 --> 00:00:07,000
Second cue first.

2
00:00:02,000 --> 00:00:04,000
First cue second.
"""
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert any(v["type"] == "out_of_order" for v in result["violations"])
        assert result["pass_qc"] is False

    def test_out_of_order_is_error_severity(self, tmp_path):
        srt = """\
1
00:00:05,000 --> 00:00:07,000
A.

2
00:00:02,000 --> 00:00:04,000
B.
"""
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        v = next(v for v in result["violations"] if v["type"] == "out_of_order")
        assert v["severity"] == "error"

    def test_overlap_detected(self, tmp_path):
        srt = """\
1
00:00:01,000 --> 00:00:04,000
First cue.

2
00:00:03,000 --> 00:00:05,000
Second cue — overlaps first.
"""
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert any(v["type"] == "overlap" for v in result["violations"])
        assert result["pass_qc"] is False

    def test_overlap_is_error_severity(self, tmp_path):
        srt = """\
1
00:00:01,000 --> 00:00:04,000
A.

2
00:00:03,000 --> 00:00:05,000
B.
"""
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        v = next(v for v in result["violations"] if v["type"] == "overlap")
        assert v["severity"] == "error"

    def test_adjacent_cues_not_overlap(self, tmp_path):
        srt = """\
1
00:00:01,000 --> 00:00:03,000
First.

2
00:00:03,000 --> 00:00:05,000
Second starts exactly when first ends.
"""
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert not any(v["type"] == "overlap" for v in result["violations"])


# ---------------------------------------------------------------------------
# 5. Duration violations
# ---------------------------------------------------------------------------


class TestDuration:
    def test_normal_duration_passes(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p, min_duration=0.5, max_duration=7.0)
        assert not any(
            v["type"].startswith("duration") for v in result["violations"]
        )

    def test_short_duration_flagged(self, tmp_path):
        srt = """\
1
00:00:01,000 --> 00:00:01,100
Too short.
"""
        p = write_srt(tmp_path, srt)
        result = run_qc(p, min_duration=0.5)
        assert any(v["type"] == "duration_too_short" for v in result["violations"])

    def test_short_duration_is_error(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:01,100\nShort.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, min_duration=0.5)
        v = next(v for v in result["violations"] if v["type"] == "duration_too_short")
        assert v["severity"] == "error"

    def test_long_duration_flagged(self, tmp_path):
        srt = """\
1
00:00:01,000 --> 00:00:10,000
This cue lasts nine seconds.
"""
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_duration=7.0)
        assert any(v["type"] == "duration_too_long" for v in result["violations"])

    def test_long_duration_is_error(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:10,000\nLong.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_duration=7.0)
        v = next(v for v in result["violations"] if v["type"] == "duration_too_long")
        assert v["severity"] == "error"

    def test_configurable_min_threshold(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:01,300\nShort.\n"
        p = write_srt(tmp_path, srt)
        # passes with generous threshold
        result_ok = run_qc(p, min_duration=0.1)
        assert not any(v["type"] == "duration_too_short" for v in result_ok["violations"])
        # fails with stricter threshold
        result_fail = run_qc(p, min_duration=0.5)
        assert any(v["type"] == "duration_too_short" for v in result_fail["violations"])

    def test_configurable_max_threshold(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:09,000\nLong cue.\n"
        p = write_srt(tmp_path, srt)
        # passes with generous threshold
        result_ok = run_qc(p, max_duration=10.0)
        assert not any(v["type"] == "duration_too_long" for v in result_ok["violations"])
        # fails with stricter threshold
        result_fail = run_qc(p, max_duration=5.0)
        assert any(v["type"] == "duration_too_long" for v in result_fail["violations"])


# ---------------------------------------------------------------------------
# 6. Reading speed (CPS)
# ---------------------------------------------------------------------------


class TestCPS:
    def test_normal_speed_passes(self, tmp_path):
        # "Hello world." = 12 chars / 2.0 s = 6 CPS — well under 20
        srt = "1\n00:00:01,000 --> 00:00:03,000\nHello world.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_cps=20.0)
        assert not any(v["type"] == "high_cps" for v in result["violations"])

    def test_high_speed_flagged(self, tmp_path):
        # 60 chars / 1.0 s = 60 CPS — way above 20
        long_text = "A" * 60
        srt = f"1\n00:00:01,000 --> 00:00:02,000\n{long_text}\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_cps=20.0)
        assert any(v["type"] == "high_cps" for v in result["violations"])

    def test_high_cps_is_warning_not_error(self, tmp_path):
        # Warnings must not flip pass_qc to False
        long_text = "A" * 100
        srt = f"1\n00:00:01,000 --> 00:00:02,000\n{long_text}\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_cps=20.0)
        v = next(v for v in result["violations"] if v["type"] == "high_cps")
        assert v["severity"] == "warning"
        assert result["pass_qc"] is True  # warnings don't fail QC
        assert result["warning_count"] > 0

    def test_configurable_cps_threshold(self, tmp_path):
        # 30 chars / 1.0 s = 30 CPS
        srt = "1\n00:00:01,000 --> 00:00:02,000\nThis is thirty characters long!!\n"
        p = write_srt(tmp_path, srt)
        # 50 CPS limit → no violation
        assert not any(
            v["type"] == "high_cps"
            for v in run_qc(p, max_cps=50.0)["violations"]
        )
        # 10 CPS limit → violation
        assert any(
            v["type"] == "high_cps"
            for v in run_qc(p, max_cps=10.0)["violations"]
        )

    def test_formatting_stripped_before_cps_calculation(self, tmp_path):
        # The override tag should not be counted as readable characters
        srt = "1\n00:00:01,000 --> 00:00:03,000\n{\\an8}Hi.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_cps=20.0)
        # "Hi." = 3 chars / 2.0 s = 1.5 CPS — no high_cps violation
        assert not any(v["type"] == "high_cps" for v in result["violations"])


# ---------------------------------------------------------------------------
# 7. Formatting artifacts
# ---------------------------------------------------------------------------


class TestFormattingArtifacts:
    def test_clean_text_passes(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p)
        assert not any(v["type"] == "formatting_artifact" for v in result["violations"])

    def test_ass_override_tag_flagged_as_error(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:03,000\n{\\an8}Text with ASS override.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        v_list = [
            v for v in result["violations"] if v["type"] == "formatting_artifact"
        ]
        assert v_list
        assert any(v["severity"] == "error" for v in v_list)

    def test_ass_override_tag_fails_qc(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:03,000\n{\\an8}Text.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert result["pass_qc"] is False

    def test_ass_inline_newline_escape_flagged(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:03,000\nLine one\\NLine two.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert any(v["type"] == "formatting_artifact" for v in result["violations"])

    def test_ass_inline_newline_is_error(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:03,000\nLine one\\NLine two.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        v = next(v for v in result["violations"] if v["type"] == "formatting_artifact")
        assert v["severity"] == "error"

    def test_html_italic_tag_flagged_as_warning(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:03,000\n<i>Italicised text.</i>\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        html_violations = [
            v
            for v in result["violations"]
            if v["type"] == "formatting_artifact" and v["severity"] == "warning"
        ]
        assert html_violations

    def test_html_tag_does_not_fail_qc(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:03,000\n<b>Bold text.</b>\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert result["pass_qc"] is True  # HTML is a warning, not an error

    def test_multiple_artifact_types_all_reported(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:03,000\n{\\an8}<i>Mixed artifacts.</i>\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        types_seen = {v["type"] for v in result["violations"]}
        assert "formatting_artifact" in types_seen


# ---------------------------------------------------------------------------
# 8. Line length and line count
# ---------------------------------------------------------------------------


class TestLineLengthAndCount:
    def test_normal_line_passes(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p, max_line_chars=42)
        assert not any(v["type"] == "line_too_long" for v in result["violations"])

    def test_long_line_flagged(self, tmp_path):
        long_line = "A" * 50
        srt = f"1\n00:00:01,000 --> 00:00:03,000\n{long_line}\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_line_chars=42)
        assert any(v["type"] == "line_too_long" for v in result["violations"])

    def test_long_line_is_warning(self, tmp_path):
        long_line = "A" * 50
        srt = f"1\n00:00:01,000 --> 00:00:03,000\n{long_line}\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_line_chars=42)
        v = next(v for v in result["violations"] if v["type"] == "line_too_long")
        assert v["severity"] == "warning"

    def test_long_line_does_not_fail_qc(self, tmp_path):
        long_line = "A" * 50
        srt = f"1\n00:00:01,000 --> 00:00:03,000\n{long_line}\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_line_chars=42)
        assert result["pass_qc"] is True

    def test_too_many_lines_flagged(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:03,000\nLine one.\nLine two.\nLine three.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_lines=2)
        assert any(v["type"] == "too_many_lines" for v in result["violations"])

    def test_too_many_lines_is_warning(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:03,000\nLine one.\nLine two.\nLine three.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_lines=2)
        v = next(v for v in result["violations"] if v["type"] == "too_many_lines")
        assert v["severity"] == "warning"

    def test_two_lines_passes(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:03,000\nLine one.\nLine two.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_lines=2)
        assert not any(v["type"] == "too_many_lines" for v in result["violations"])

    def test_configurable_line_char_limit(self, tmp_path):
        # 34 chars
        srt = "1\n00:00:01,000 --> 00:00:03,000\nExactly thirty-four characters ok!\n"
        p = write_srt(tmp_path, srt)
        # passes at 42
        assert not any(
            v["type"] == "line_too_long"
            for v in run_qc(p, max_line_chars=42)["violations"]
        )
        # fails at 20
        assert any(
            v["type"] == "line_too_long"
            for v in run_qc(p, max_line_chars=20)["violations"]
        )


# ---------------------------------------------------------------------------
# Summary structure
# ---------------------------------------------------------------------------


class TestSummaryStructure:
    def test_summary_has_all_required_keys(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p)
        for key in (
            "parsed_ok",
            "cue_count",
            "violations",
            "error_count",
            "warning_count",
            "pass_qc",
        ):
            assert key in result, f"Missing key: {key}"

    def test_pass_qc_true_for_clean_file(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p)
        assert result["pass_qc"] is True
        assert result["error_count"] == 0

    def test_pass_qc_false_when_errors_present(self, tmp_path):
        srt = """\
1
00:00:05,000 --> 00:00:07,000
Second.

2
00:00:02,000 --> 00:00:04,000
First.
"""
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert result["pass_qc"] is False
        assert result["error_count"] > 0

    def test_each_violation_has_required_keys(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:01,100\nShort cue.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        for v in result["violations"]:
            for key in ("type", "severity", "cue_index", "detail"):
                assert key in v, f"Violation missing key '{key}': {v}"

    def test_error_count_matches_error_violations(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:01,100\nShort.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert result["error_count"] == sum(
            1 for v in result["violations"] if v["severity"] == "error"
        )

    def test_warning_count_matches_warning_violations(self, tmp_path):
        long_line = "A" * 50
        srt = f"1\n00:00:01,000 --> 00:00:03,000\n{long_line}\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p, max_line_chars=42)
        assert result["warning_count"] == sum(
            1 for v in result["violations"] if v["severity"] == "warning"
        )

    def test_violations_is_empty_list_for_clean_file(self, tmp_path):
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p)
        assert isinstance(result["violations"], list)
        assert result["violations"] == []

    def test_summary_is_json_serialisable(self, tmp_path):
        import json
        p = write_srt(tmp_path, MINIMAL_SRT)
        result = run_qc(p)
        # Should not raise
        serialised = json.dumps(result)
        assert isinstance(serialised, str)

    def test_violations_list_for_error_file(self, tmp_path):
        srt = "1\n00:00:01,000 --> 00:00:01,100\nShort.\n"
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        assert isinstance(result["violations"], list)
        assert len(result["violations"]) > 0

    def test_cue_index_in_violation_matches_sequence_number(self, tmp_path):
        # The second cue (sequence 2) has the overlap
        srt = """\
1
00:00:01,000 --> 00:00:04,000
A.

2
00:00:03,000 --> 00:00:05,000
B.
"""
        p = write_srt(tmp_path, srt)
        result = run_qc(p)
        overlap_v = next(v for v in result["violations"] if v["type"] == "overlap")
        assert overlap_v["cue_index"] == 2
