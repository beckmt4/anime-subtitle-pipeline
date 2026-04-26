"""Tests for subtitle_utils extract_subtitle_track.

Creates a tiny video + SRT, muxes the subtitle, then extracts and parses.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
import sys

import pytest

from media_inspect import inspect_media
from subtitle_utils import extract_subtitle_track

TEMP_DIR = Path("temp").resolve()
TEMP_DIR.mkdir(parents=True, exist_ok=True)

VIDEO = TEMP_DIR / "subtitle_test_source.mp4"
SRT = TEMP_DIR / "subtitle_test.srt"
MUXED = TEMP_DIR / "subtitle_test_muxed.mkv"


def create_sample_video():
    if VIDEO.exists():
        return
    cmd = [
        "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=2",
        "-f", "lavfi", "-i", "anullsrc",
        "-c:v", "libx264", "-t", "2", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-y", str(VIDEO)
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)


def create_sample_srt():
    if SRT.exists():
        return
    content = """1\n00:00:00,000 --> 00:00:01,000\nHello world!\n\n2\n00:00:01,000 --> 00:00:02,000\nGoodbye!\n"""
    SRT.write_text(content, encoding="utf-8")


def mux_subtitle():
    if MUXED.exists():
        return
    cmd = [
        "ffmpeg", "-i", str(VIDEO), "-i", str(SRT),
        "-c", "copy", "-c:s", "srt", "-y", str(MUXED)
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)


@pytest.mark.integration
def test_extract():
    create_sample_video()
    create_sample_srt()
    mux_subtitle()

    media = inspect_media(str(MUXED))
    assert media.subtitle_streams, "Expected at least one embedded subtitle track"
    stream = media.subtitle_streams[0]
    # Language might be None since we didn't tag; treat as 'und'
    lang = stream.language or "und"
    candidate = extract_subtitle_track(MUXED, stream.index, lang)
    assert candidate.source == "embedded", "Source mismatch"
    assert candidate.language == lang, "Language mismatch"
    assert candidate.origin_stream == f"sub:{stream.index}", "Origin stream mismatch"
    assert candidate.segments, "No segments parsed from extracted subtitle"
    assert candidate.meta.get("file"), "Meta file missing"
    print("Extracted candidate:", candidate)


if __name__ == "__main__":
    try:
        test_extract()
        print("Subtitle extraction test passed")
        sys.exit(0)
    except Exception as e:
        print("Subtitle extraction test failed:", e)
        sys.exit(1)
