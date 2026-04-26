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
        self._data = {
            "asr": {
                "model_name": "large-v3-turbo",
                "device": "cpu",
                "compute_type": "int8_float16",
                "beam_size": 5,
                "vad_filter": False,
            }
        }

    # Provide attribute properties accessed in builder
    @property
    def asr_model_name(self):
        return self._data["asr"]["model_name"]

    @property
    def asr_compute_type(self):
        return self._data["asr"]["compute_type"]

    @property
    def asr_beam_size(self):
        return self._data["asr"]["beam_size"]

    @property
    def asr_vad_filter(self):
        return self._data["asr"]["vad_filter"]


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

    logger.info("✓ ASR candidate builder tests passed")
    return True


if __name__ == "__main__":
    ok = test_candidate_builder()
    logger.info("Result: %s", "PASS" if ok else "FAIL")
    import sys
    sys.exit(0 if ok else 1)
