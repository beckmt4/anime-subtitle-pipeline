"""Deterministic review-task routing tests."""

from __future__ import annotations

from core.review import route_benchmark_review_task, route_generate_review_task


def test_generate_invalid_srt_routes_to_failed() -> None:
    result = route_generate_review_task(
        video="sample.mkv",
        candidate_id="cand-1",
        strategy="ja_audio_asr_mt",
        qc_summary={
            "parsed_ok": False,
            "cue_count": 0,
            "violations": [{"type": "parse_failed", "severity": "error"}],
            "error_count": 1,
            "warning_count": 0,
        },
        candidate_score={"total_score": 72.0},
        selection_report={"review_recommended": False},
        routing_decision={"decision": "pass"},
    )
    assert result["status"] == "failed"
    assert "generate.invalid_or_zero_cues" in result["reason_codes"]
    assert result["review_task"] is not None


def test_generate_repeated_readability_issues_route_to_review_required() -> None:
    result = route_generate_review_task(
        video="sample.mkv",
        candidate_id="cand-2",
        strategy="embedded_en",
        qc_summary={
            "parsed_ok": True,
            "cue_count": 12,
            "violations": [
                {"type": "high_cps", "severity": "warning"},
                {"type": "high_cps", "severity": "warning"},
                {"type": "high_cps", "severity": "warning"},
            ],
            "error_count": 0,
            "warning_count": 3,
        },
        candidate_score={"total_score": 80.0},
        selection_report={"review_recommended": False},
        routing_decision={"decision": "pass"},
    )
    assert result["status"] == "review_required"
    assert "generate.high_cps_repeated" in result["reason_codes"]
    assert result["review_task"] is not None


def test_benchmark_weak_comparisons_route_to_review_required() -> None:
    result = route_benchmark_review_task(
        video="bench.mkv",
        results={
            "run_id": "run-1",
            "reference_id": "embedded_en_s0",
            "status": "ok",
            "comparisons": [
                {
                    "ref_id": "embedded_en_s0",
                    "cand_id": "ja_audio_asr_mt_a1",
                    "metrics": {"wer": 0.62, "bleu": 12.0, "chrf": 25.0},
                }
            ],
        },
    )
    assert result["status"] == "review_required"
    assert "benchmark.quality_below_threshold" in result["reason_codes"]
    assert result["review_task"] is not None

