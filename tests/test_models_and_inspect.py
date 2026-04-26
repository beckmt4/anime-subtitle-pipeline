"""Lightweight tests for `models` and `media_inspect` modules.

Run standalone: `python tests/test_models_and_inspect.py [optional_video_path]`
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from models import Segment, SubtitleCandidate
from media_inspect import inspect_media, MediaInfo

logger = logging.getLogger(__name__)


def test_models():
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
    assert abs(candidate.duration - 3.0) < 1e-6, "Total duration mismatch"


def test_media_inspect(video_path: Path = None):
    if video_path is None:
        sample = Path("temp/kiki_sample_2min.mkv")
        video_path = sample if sample.exists() else None

    if video_path is None or not video_path.exists():
        pytest.skip("No media file available for inspection")

    info: MediaInfo = inspect_media(str(video_path))
    assert info.path.exists(), "MediaInfo path invalid"
    for a in info.audio_streams:
        assert a.index >= 0, "Audio index negative"
        assert a.codec, "Audio codec empty"
    for s in info.subtitle_streams:
        assert s.index >= 0, "Subtitle index negative"
        assert s.codec, "Subtitle codec empty"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    passed = True

    try:
        test_models()
        logger.info("models: PASS")
    except AssertionError as e:
        logger.error("models: FAIL — %s", e)
        passed = False

    try:
        test_media_inspect(Path(arg) if arg else None)
        logger.info("media_inspect: PASS")
    except BaseException as e:  # catches pytest.skip.Exception too
        if "skip" in type(e).__name__.lower() or "Skipped" in type(e).__name__:
            logger.warning("media_inspect: SKIP (no video file)")
        else:
            logger.error("media_inspect: FAIL — %s", e)
            passed = False

    sys.exit(0 if passed else 1)
