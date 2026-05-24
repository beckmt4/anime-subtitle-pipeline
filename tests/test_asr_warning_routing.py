"""ASR warning density scoring and routing tests."""

from __future__ import annotations

from config import Config
from core.subtitles import Segment, SubtitleCandidate
from orchestrator import score_candidate
from core.policy import PolicyEngine


def _candidate(count: int = 20) -> SubtitleCandidate:
    return SubtitleCandidate(
        id="en_audio_asr_a0",
        language="en",
        source="asr",
        origin_stream="audio:0",
        segments=[
            Segment(float(i), float(i + 1), f"line {i}")
            for i in range(count)
        ],
        meta={},
    )


def _qc_summary(cue_count: int, asr_warnings: int) -> dict:
    return {
        "parsed_ok": True,
        "cue_count": cue_count,
        "violations": [
            {
                "type": "asr_low_confidence",
                "severity": "warning",
                "cue_index": i + 1,
                "detail": "ASR warning repeated_text: text repeats",
            }
            for i in range(asr_warnings)
        ],
        "error_count": 0,
        "warning_count": asr_warnings,
        "pass_qc": True,
    }


def test_score_candidate_penalizes_asr_warning_density():
    clean = score_candidate("en_audio_asr", _candidate(), _qc_summary(20, 0))
    noisy = score_candidate("en_audio_asr", _candidate(), _qc_summary(20, 5))

    assert noisy["asr_warning_density"] == 0.25
    factor = next(f for f in noisy["factors"] if f["name"] == "asr_warning_density")
    assert factor["contribution"] < 0
    assert noisy["total_score"] < clean["total_score"]


def test_policy_routes_high_asr_warning_density_to_review():
    cfg = Config()
    cfg._config.setdefault("policy", {})
    cfg._config["policy"]["routing"] = {
        "review_score_threshold": 60,
        "reject_score_threshold": 20,
        "asr_warning_review_density": 0.10,
    }
    engine = PolicyEngine(cfg)
    score = {
        "total_score": 80.0,
        "grade": "A",
        "asr_warning_density": 0.25,
    }
    report = {"review_recommended": False, "review_reason": None}

    result = engine.route(score, report)

    assert result["decision"] == "review"
    assert "asr_warning_density" in result["triggered_by"]
