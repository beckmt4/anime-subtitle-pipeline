"""ASR confidence metadata propagation tests."""

from __future__ import annotations

from core.subtitles import Segment, SubtitleCandidate
from core.mt import MarianTranslator
from subtitle_qc import run_qc


class StubConfig:
    profile = "dev"

    @property
    def mt_model_name(self):
        return "stub-mt"

    @property
    def mt_batch_size(self):
        return 16

    @property
    def mt_device(self):
        return "cpu"

    def get(self, *keys, default=None):
        return default


def test_mt_candidate_preserves_asr_segment_and_summary_metadata():
    asr_warning = {
        "type": "low_average_log_probability",
        "severity": "warning",
        "detail": "avg_logprob -2.00 < -1.00",
    }
    candidate = SubtitleCandidate(
        id="asr_ja",
        language="ja",
        source="asr",
        origin_stream="audio:0",
        segments=[
            Segment(
                0.0,
                1.0,
                "???",
                meta={"asr": {"low_confidence": True, "warnings": [asr_warning]}},
            )
        ],
        meta={
            "asr_quality": {
                "status": "warn",
                "segment_count": 1,
                "low_confidence_segment_count": 1,
                "warning_count": 1,
            },
            "asr_quality_status": "warn",
            "asr_low_confidence_segment_count": 1,
        },
    )
    translator = MarianTranslator(StubConfig())
    translator.translate_batch = lambda texts: ["uncertain line"]

    translated = translator.translate_candidate(candidate)

    assert translated.meta["asr_quality"]["low_confidence_segment_count"] == 1
    assert translated.meta["asr_low_confidence_segment_count"] == 1
    assert translated.segments[0].meta["asr"]["warnings"][0]["type"] == "low_average_log_probability"


def test_qc_includes_asr_origin_warnings(tmp_path):
    srt = tmp_path / "test.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nUncertain line.\n",
        encoding="utf-8",
    )
    candidate = SubtitleCandidate(
        id="asr_ja_mt",
        language="en",
        source="mt",
        origin_stream="audio:0",
        segments=[
            Segment(
                1.0,
                3.0,
                "Uncertain line.",
                meta={
                    "asr": {
                        "low_confidence": True,
                        "warnings": [
                            {
                                "type": "high_no_speech_probability",
                                "severity": "warning",
                                "detail": "no_speech_prob 0.80 > 0.60",
                            }
                        ],
                    }
                },
            )
        ],
        meta={},
    )

    result = run_qc(srt, candidate=candidate)

    assert result["pass_qc"] is True
    assert any(v["type"] == "asr_low_confidence" for v in result["violations"])
