"""Tests for translation_qc.run_translation_qc."""

from __future__ import annotations

from models import Segment, SubtitleCandidate
from translation_qc import run_translation_qc


class DummyConfig:
    def __init__(self, data=None):
        self._data = data or {}

    def get(self, *keys, default=None):
        value = self._data
        for key in keys:
            if not isinstance(value, dict):
                return default
            value = value.get(key)
            if value is None:
                return default
        return value


def _candidate(candidate_id: str, text: str, *, meta=None, language: str = "en"):
    return SubtitleCandidate(
        id=candidate_id,
        language=language,
        source="test",
        origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, text, meta=meta or {})],
        meta={},
    )


def test_translation_qc_pass_case():
    source = _candidate("ja_src", "太郎は東京駅へ行く。", language="ja")
    literal = _candidate("lit", "Taro goes to Tokyo Station.")
    final = _candidate("fin", "Taro goes to Tokyo Station.")

    result = run_translation_qc(final, source_candidate=source, literal_candidate=literal)

    assert result["qc_status"] == "pass"
    assert result["findings"] == []
    assert result["summary"]["fail_count"] == 0


def test_translation_qc_warn_case_for_possible_omission():
    source = _candidate("ja_src", "今日は本当に大事な話をしないといけない", language="ja")
    final = _candidate(
        "fin",
        "Okay.",
        meta={"source_text_ja": "今日は本当に大事な話をしないといけない"},
    )
    cfg = DummyConfig({"translation_qc": {"warn_min_ratio": 0.60, "fail_min_ratio": 0.10}})

    result = run_translation_qc(final, source_candidate=source, config=cfg)

    assert result["qc_status"] == "warn"
    assert any(f["code"] == "possible_omission" for f in result["findings"])
    assert result["segment_results"][0]["review_required"] is True


def test_translation_qc_fail_case_for_empty_final_line():
    source = _candidate("ja_src", "これは重要です", language="ja")
    final = _candidate("fin", "")

    result = run_translation_qc(final, source_candidate=source)

    assert result["qc_status"] == "fail"
    assert any(f["code"] == "missing_final_line" for f in result["findings"])
    assert result["summary"]["fail_count"] >= 1


def test_translation_qc_uses_mocked_llm_judge():
    source = _candidate("ja_src", "そういうことだ", language="ja")
    final = _candidate("fin", "That's it.")
    cfg = DummyConfig({"translation_qc": {"llm_judge": {"enabled": True}}})

    def _mock_judge(payload):
        assert payload["candidate_id"] == "fin"
        return {
            "findings": [
                {
                    "segment_index": 1,
                    "severity": "warning",
                    "code": "possible_context_hallucination",
                    "message": "May add unsupported context",
                }
            ]
        }

    result = run_translation_qc(final, source_candidate=source, config=cfg, llm_judge=_mock_judge)

    assert result["qc_status"] in {"warn", "fail"}
    assert any(f["code"] == "possible_context_hallucination" for f in result["findings"])
