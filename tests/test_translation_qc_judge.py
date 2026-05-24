"""Tests for translation judge heuristics in subtitle_qc."""

from __future__ import annotations

from core.subtitles import Segment, SubtitleCandidate
from subtitle_qc import run_qc


def _write_single_cue(tmp_path, text: str):
    srt = tmp_path / "judge.srt"
    srt.write_text(
        f"1\n00:00:01,000 --> 00:00:03,000\n{text}\n",
        encoding="utf-8",
    )
    return srt


def test_qc_flags_possible_omission_for_short_translation(tmp_path):
    srt = _write_single_cue(tmp_path, "Ok.")
    candidate = SubtitleCandidate(
        id="ja_mt",
        language="en",
        source="mt",
        origin_stream="sub:0",
        segments=[
            Segment(
                1.0,
                3.0,
                "Ok.",
                meta={"source_text_ja": "今日は本当に大事な話をしないといけない"},
            )
        ],
        meta={},
    )

    result = run_qc(srt, candidate=candidate)

    assert any(v["type"] == "translation_possible_omission" for v in result["violations"])


def test_qc_flags_possible_added_meaning_for_overlong_translation(tmp_path):
    text = "I will explain every single hidden reason in complete detail right now."
    srt = _write_single_cue(tmp_path, text)
    candidate = SubtitleCandidate(
        id="ja_mt",
        language="en",
        source="mt",
        origin_stream="sub:0",
        segments=[
            Segment(1.0, 3.0, text, meta={"source_text_ja": "だめだ"})
        ],
        meta={},
    )

    result = run_qc(srt, candidate=candidate)

    assert any(v["type"] == "translation_possible_added_meaning" for v in result["violations"])


def test_qc_flags_softened_adult_dialogue_for_live_action_profile(tmp_path):
    srt = _write_single_cue(tmp_path, "Let's do that.")
    candidate = SubtitleCandidate(
        id="ja_mt",
        language="en",
        source="mt",
        origin_stream="sub:0",
        segments=[
            Segment(1.0, 3.0, "Let's do that.", meta={"source_text_ja": "セックスしよう"})
        ],
        meta={"translation_dialogue_profile": "live_action_adult"},
    )

    result = run_qc(srt, candidate=candidate)

    assert any(
        v["type"] == "translation_possible_softened_adult_dialogue"
        for v in result["violations"]
    )


def test_qc_flags_untranslated_output_when_cjk_present(tmp_path):
    srt = _write_single_cue(tmp_path, "日本語のまま")
    candidate = SubtitleCandidate(
        id="ja_mt",
        language="en",
        source="mt",
        origin_stream="sub:0",
        segments=[
            Segment(1.0, 3.0, "日本語のまま", meta={"source_text_ja": "日本語のまま"})
        ],
        meta={},
    )

    result = run_qc(srt, candidate=candidate)

    assert any(v["type"] == "translation_possible_untranslated" for v in result["violations"])


def test_qc_flags_low_confidence_marker_for_review(tmp_path):
    srt = _write_single_cue(tmp_path, "[LOW_CONFIDENCE] I'm not sure what he said.")
    candidate = SubtitleCandidate(
        id="ja_mt",
        language="en",
        source="mt",
        origin_stream="sub:0",
        segments=[
            Segment(
                1.0,
                3.0,
                "[LOW_CONFIDENCE] I'm not sure what he said.",
                meta={"source_text_ja": "……よく聞き取れない"},
            )
        ],
        meta={"translation_dialogue_profile": "live_action_adult"},
    )

    result = run_qc(srt, candidate=candidate)

    assert any(
        v["type"] == "translation_low_confidence_flagged"
        for v in result["violations"]
    )


def test_qc_flags_high_risk_content_for_manual_review(tmp_path):
    text = "[REVIEW_HIGH_RISK] She's underage, force her."
    srt = _write_single_cue(tmp_path, text)
    candidate = SubtitleCandidate(
        id="ja_mt",
        language="en",
        source="mt",
        origin_stream="sub:0",
        segments=[
            Segment(1.0, 3.0, text, meta={"source_text_ja": "未成年だ、無理やりやれ"})
        ],
        meta={"translation_dialogue_profile": "live_action_adult"},
    )

    result = run_qc(srt, candidate=candidate)

    assert any(
        v["type"] == "translation_high_risk_content_review"
        for v in result["violations"]
    )
