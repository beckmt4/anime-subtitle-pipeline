"""Test ASR refactor candidate creation without running heavy model.

This test focuses on the conversion of legacy ASR `Segment` objects into
the new generic `SubtitleCandidate` structure. It does NOT invoke the
Faster-Whisper model to avoid long runtimes.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass
from typing import List

from config import Config
from asr import Segment, build_candidate_from_segments

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Minimal stub config replacement if actual Config load is undesired.
class StubConfig(Config):  # inherits to reuse attribute access patterns
    def __init__(self):
        # Bypass file loading; set required attributes directly
        self.config_path = "<stub>"
        self.profile = "dev"
        self._config = {
            "asr": {
                "model_name": "large-v3-turbo",
                "device": "cpu",
                "compute_type": "int8_float16",
                "beam_size": 5,
                "vad_filter": False,
                "quality": {
                    "warn_no_speech_prob_above": 0.60,
                    "warn_avg_logprob_below": -1.00,
                    "warn_compression_ratio_above": 2.40,
                    "warn_min_duration_sec": 0.25,
                    "warn_max_duration_sec": 12.0,
                    "warn_gap_sec": 6.0,
                    "warn_repeated_text_count": 3,
                    "warn_japanese_char_ratio_below": 0.20,
                    "fail_low_confidence_ratio": 0.50,
                },
            }
        }

    # Provide attribute properties accessed in builder
    @property
    def asr_model_name(self):
        return self._config["asr"]["model_name"]

    @property
    def asr_compute_type(self):
        return self._config["asr"]["compute_type"]

    @property
    def asr_beam_size(self):
        return self._config["asr"]["beam_size"]

    @property
    def asr_vad_filter(self):
        return self._config["asr"]["vad_filter"]


def test_candidate_builder() -> bool:
    logger.info("Testing ASR candidate builder...")
    segments: List[Segment] = [
        Segment(0.0, 1.2, "こんにちは"),
        Segment(1.2, 2.7, "世界"),
    ]
    config = StubConfig()
    candidate = build_candidate_from_segments(segments, config)

    assert candidate.id == "asr_ja", "Candidate ID mismatch"
    assert candidate.language == "ja", "Language mismatch"
    assert candidate.source == "asr", "Source mismatch"
    assert candidate.segment_count == 2, "Segment count mismatch"
    assert abs(candidate.total_duration - 2.7) < 1e-6, "Total duration mismatch"
    assert candidate.meta.get("asr_model") == "large-v3-turbo", "Meta model name mismatch"
    assert candidate.meta["asr_quality"]["status"] == "clean"
    assert candidate.meta["asr_low_confidence_segment_count"] == 0
    assert candidate.segments[0].meta["asr"]["low_confidence"] is False

    logger.info("✓ ASR candidate builder tests passed")
    return True


def test_candidate_builder_flags_weak_asr_segments():
    segments = [
        Segment(
            0.0,
            0.1,
            "???",
            avg_logprob=-2.0,
            no_speech_prob=0.80,
            compression_ratio=3.1,
        ),
        Segment(0.2, 1.2, "こんにちは", avg_logprob=-0.1, no_speech_prob=0.05),
    ]
    candidate = build_candidate_from_segments(segments, StubConfig())

    assert candidate.meta["asr_quality"]["status"] == "fail"
    assert candidate.meta["asr_low_confidence_segment_count"] == 1
    warnings = candidate.segments[0].meta["asr"]["warnings"]
    warning_types = {w["type"] for w in warnings}
    assert "high_no_speech_probability" in warning_types
    assert "low_average_log_probability" in warning_types
    assert "high_compression_ratio" in warning_types
    assert "very_short_segment" in warning_types
    assert "low_japanese_character_ratio" in warning_types


def test_candidate_builder_empty_asr_is_fail_status():
    candidate = build_candidate_from_segments([], StubConfig())

    assert candidate.meta["asr_quality"]["status"] == "fail"
    assert candidate.meta["asr_quality"]["summary_warnings"][0]["type"] == "no_speech_segments"


if __name__ == "__main__":
    ok = test_candidate_builder()
    logger.info("Result: %s", "PASS" if ok else "FAIL")
    import sys
    sys.exit(0 if ok else 1)
