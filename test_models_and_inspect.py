"""Lightweight tests for `models` and `media_inspect` modules.

Run standalone: `python test_models_and_inspect.py [optional_video_path]`
Falls back to `temp/kiki_sample_2min.mkv` if no path supplied and file exists.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from models import Segment, SubtitleCandidate
from media_inspect import inspect_media, MediaInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_models() -> bool:
    logger.info("Testing models...")
    seg1 = Segment(0.0, 1.5, "Hello world")
    seg2 = Segment(1.5, 3.0, "Goodbye")
    assert abs(seg1.duration - 1.5) < 1e-6, "Segment duration incorrect"
    assert abs(seg2.duration - 1.5) < 1e-6, "Segment duration incorrect"

    candidate = SubtitleCandidate(
        id="asr_ja",
        language="ja",
        source="asr",
        origin_stream="audio:0",
        segments=[seg1, seg2],
        meta={"model": "faster-whisper-large-v3-turbo"},
    )
    assert candidate.count == 2, "Segment count mismatch"
    total = candidate.duration
    assert abs(total - 3.0) < 1e-6, "Total duration mismatch"
    logger.info("✓ models tests passed")
    return True


def test_media_inspect(video_path: Path = None) -> bool:
    logger.info("Testing media inspection...")
    if video_path is None:
        # Attempt default sample path
        sample = Path("temp/kiki_sample_2min.mkv")
        video_path = sample if sample.exists() else None

    if video_path is None or not video_path.exists():
        logger.warning("No media file available for inspection; skipping.")
        return True  # skip does not fail

    try:
        info: MediaInfo = inspect_media(str(video_path))
        logger.info(
            "✓ inspected '%s': %d audio, %d subs", video_path.name, len(info.audio_streams), len(info.subtitle_streams)
        )
        # Basic sanity assertions
        assert info.path.exists(), "MediaInfo path invalid"
        for a in info.audio_streams:
            assert a.index >= 0, "Audio index negative"
            assert a.codec, "Audio codec empty"
        for s in info.subtitle_streams:
            assert s.index >= 0, "Subtitle index negative"
            assert s.codec, "Subtitle codec empty"
        return True
    except Exception as e:
        logger.error(f"Media inspection failed: {e}")
        return False


def run_all(video_arg: str | None) -> bool:
    results = {
        "models": test_models(),
        "media_inspect": test_media_inspect(Path(video_arg) if video_arg else None),
    }
    passed = all(results.values())
    logger.info("\nTest Summary:")
    for name, ok in results.items():
        logger.info("%s: %s", name, "PASS" if ok else "FAIL")
    if passed:
        logger.info("\n✓ All new module tests passed")
    else:
        logger.info("\n⚠ Failures detected in new module tests")
    return passed


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    success = run_all(arg)
    sys.exit(0 if success else 1)
