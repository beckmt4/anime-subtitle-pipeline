"""Utilities for working with embedded subtitle tracks.

Provides functions to demux subtitle streams from a container and
convert them into generic `SubtitleCandidate` objects using the
shared `Segment` dataclass.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List

import pysubs2

from core.ocr import OCRBackend, ocr_subtitle_track
from core.subtitles import Segment, SubtitleCandidate
from media_inspect import inspect_media, MediaInfo, SubtitleStream

logger = logging.getLogger(__name__)


_SIDECAR_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt")
_LANG_TOKENS = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "ja": "ja",
    "jpn": "ja",
    "japanese": "ja",
}


def _normalize_subtitle_text(text: str) -> str:
    return text.replace("\\N", "\n").strip()


def parse_subtitle_file(path: Path) -> List[Segment]:
    """Parse a subtitle file into generic `Segment` objects.

    Uses pysubs2 to handle timing conversion. Milliseconds converted to seconds.
    Empty/whitespace-only lines are skipped.
    """
    subs = pysubs2.load(str(path), encoding="utf-8")
    segments: List[Segment] = []
    for line in subs:
        text = _normalize_subtitle_text(line.text or "")
        if not text:
            continue
        start = line.start / 1000.0
        end = line.end / 1000.0
        segments.append(Segment(start=start, end=end, text=text))
    return segments


def parse_srt(path: Path) -> List[Segment]:
    return parse_subtitle_file(path)


def _infer_sidecar_language(sidecar_path: Path) -> str:
    tokens = sidecar_path.stem.lower().replace("-", ".").replace("_", ".").split(".")
    for token in reversed(tokens):
        if token in _LANG_TOKENS:
            return _LANG_TOKENS[token]
    return "und"


def discover_sidecar_subtitles(video: Path | str) -> List[SubtitleCandidate]:
    """Discover sidecar subtitle files next to *video* and normalize them."""
    video_path = Path(video).resolve()
    if not video_path.exists():
        return []

    candidates: List[SubtitleCandidate] = []
    seen: set[Path] = set()
    for ext in _SIDECAR_EXTENSIONS:
        for file_path in sorted(video_path.parent.glob(f"{video_path.stem}*{ext}")):
            if file_path in seen:
                continue
            seen.add(file_path)
            segments = parse_subtitle_file(file_path)
            if not segments:
                continue
            language = _infer_sidecar_language(file_path)
            candidates.append(
                SubtitleCandidate(
                    id=f"sidecar_{language}_{file_path.stem}",
                    language=language,
                    source="sidecar",
                    origin_stream=f"sidecar:{file_path.name}",
                    segments=segments,
                    meta={
                        "file": str(file_path),
                        "format": file_path.suffix.lower().lstrip("."),
                        "normalization": "pysubs2",
                    },
                )
            )

    return candidates


def _subtitle_order_from_global(media: MediaInfo, global_index: int) -> int:
    """Translate a global stream index to subtitle-order index for ffmpeg mapping."""
    for order, stream in enumerate(media.subtitle_streams):
        if stream.index == global_index:
            return order
    raise ValueError(f"Global subtitle stream index {global_index} not found in media")


def extract_subtitle_track(
    video: Path | str,
    sub_index: int,
    language: str,
    output_dir: Path | None = None,
    ocr_backend: OCRBackend | None = None,
) -> SubtitleCandidate:
    """Demux a subtitle track and return as `SubtitleCandidate`.

    Args:
        video: Input video file path.
        sub_index: Global stream index from `MediaInfo.subtitle_streams[i].index`.
        language: Normalized language code to assign.
        output_dir: Optional directory for extracted SRT (defaults next to video).

    Returns:
        SubtitleCandidate representing the embedded subtitle track.
    """
    video_path = Path(video).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not video_path.is_file():
        raise ValueError(f"Path is not a file: {video_path}")

    media = inspect_media(str(video_path))
    # Locate stream & determine order index for ffmpeg -map 0:s:ORDER mapping
    stream: SubtitleStream | None = None
    for s in media.subtitle_streams:
        if s.index == sub_index:
            stream = s
            break
    if stream is None:
        raise ValueError(f"Subtitle stream with global index {sub_index} not found")
    order_index = _subtitle_order_from_global(media, sub_index)

    if stream.is_bitmap:
        if ocr_backend is None:
            raise RuntimeError(
                f"Subtitle stream {sub_index} is bitmap codec '{stream.codec}' "
                "(OCR backend not configured)"
            )
        candidate = ocr_subtitle_track(
            str(video_path),
            sub_index,
            ocr_backend,
            language_hint=language,
        )
        candidate.meta.setdefault("codec", stream.codec)
        candidate.meta.setdefault("global_index", sub_index)
        return candidate

    # Derive output path
    out_dir = output_dir or video_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_srt = out_dir / f"{video_path.stem}.track{sub_index}.{language}.srt"

    logger.info(
        "Demuxing subtitle stream global=%d order=%d codec=%s to %s",
        sub_index,
        order_index,
        stream.codec,
        out_srt.name,
    )

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-map", f"0:s:{order_index}",
        "-c:s", "srt",
        "-y",
        str(out_srt),
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg subtitle demux failed: {e.stderr or e}") from e

    if not out_srt.exists():
        raise RuntimeError("Demux completed but SRT file missing")

    segments = parse_subtitle_file(out_srt)
    if not segments:
        logger.warning("Extracted subtitle track produced no segments: %s", out_srt.name)

    candidate = SubtitleCandidate(
        id=f"embedded_{language}_s{sub_index}",
        language=language,
        source="embedded",
        origin_stream=f"sub:{sub_index}",
        segments=segments,
        meta={
            "file": str(out_srt),
            "codec": stream.codec,
            "global_index": sub_index,
        },
    )

    return candidate


__all__ = [
    "extract_subtitle_track",
    "parse_srt",
    "parse_subtitle_file",
    "discover_sidecar_subtitles",
]
