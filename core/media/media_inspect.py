"""Media inspection utilities.

Wraps ffprobe to parse media containers into structured metadata.
All language-code normalization here is protocol-level (ISO-639 mapping)
and must not contain language-pack-specific aliases.
``core.media.__init__`` re-exports from this module.

Public API
----------
inspect_media(path)           → MediaInfo
MediaInfo                     Parsed container info with stream lists.
AudioStream                   Single audio stream descriptor.
SubtitleStream                Single subtitle stream descriptor.
choose_audio_track(media, …)  → int   priority-list-based selection
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


LANG_MAP = {
    "jpn": "ja",
    "ja": "ja",
    "japanese": "ja",
    "eng": "en",
    "en": "en",
    "english": "en",
    "fre": "fr",
    "fra": "fr",
    "french": "fr",
    "chi": "zh",
    "zho": "zh",
    "chinese": "zh",
    "und": "und",
}


def _norm_lang(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    c = code.lower()
    return LANG_MAP.get(c, c)


@dataclass
class StreamBase:
    index: int
    codec: str
    language: Optional[str] = None
    raw_language: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class AudioStream(StreamBase):
    channels: int = 2
    sample_rate: int = 48000


@dataclass
class SubtitleStream(StreamBase):
    is_bitmap: bool = False


@dataclass
class MediaInfo:
    path: Path
    format_name: str
    duration: Optional[float]
    audio_streams: List[AudioStream] = field(default_factory=list)
    subtitle_streams: List[SubtitleStream] = field(default_factory=list)

    def audio_summary(self) -> str:
        return ", ".join(
            f"a:{i} idx={s.index} {s.codec} {s.channels}ch {s.sample_rate}Hz lang={s.language or '-'}"
            for i, s in enumerate(self.audio_streams)
        ) or "<none>"

    def subtitle_summary(self) -> str:
        return ", ".join(
            f"s:{i} idx={s.index} {s.codec} lang={s.language or '-'} bitmap={'yes' if s.is_bitmap else 'no'}"
            for i, s in enumerate(self.subtitle_streams)
        ) or "<none>"


def inspect_media(path: str) -> MediaInfo:
    """Run ffprobe on the given media file and return structured info."""
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Media file not found: {p}")
    if not p.is_file():
        raise ValueError(f"Path is not a file: {p}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(p),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e.stderr or e}") from e

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ffprobe JSON: {e}") from e

    fmt = data.get("format", {})
    format_name = fmt.get("format_name", "unknown")
    duration = None
    if "duration" in fmt:
        try:
            duration = float(fmt["duration"])
        except ValueError:
            duration = None

    info = MediaInfo(path=p, format_name=format_name, duration=duration)

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        index = stream.get("index", -1)
        codec = stream.get("codec_name", "unknown")
        tags = stream.get("tags", {}) or {}
        raw_language = tags.get("language")
        language = _norm_lang(raw_language)

        if codec_type == "audio":
            a = AudioStream(
                index=index,
                codec=codec,
                channels=stream.get("channels", 2),
                sample_rate=int(stream.get("sample_rate", 48000)),
                language=language,
                raw_language=raw_language,
                tags={k: str(v) for k, v in tags.items()},
            )
            info.audio_streams.append(a)
        elif codec_type == "subtitle":
            is_bitmap = codec in {"dvd_subtitle", "pgssub", "xsub"}
            s = SubtitleStream(
                index=index,
                codec=codec,
                language=language,
                raw_language=raw_language,
                tags={k: str(v) for k, v in tags.items()},
                is_bitmap=is_bitmap,
            )
            info.subtitle_streams.append(s)

    logger.debug(
        "Inspected media '%s': format=%s duration=%.2fs audio=[%s] subs=[%s]",
        info.path.name,
        info.format_name,
        info.duration or -1.0,
        info.audio_summary(),
        info.subtitle_summary(),
    )

    return info


def choose_audio_track(media: MediaInfo, preferred_languages: Optional[List[str]] = None) -> int:
    """Select an audio-order index based on preferred languages."""
    if not media.audio_streams:
        return 0
    preferred_languages = preferred_languages or ["ja", "jpn"]
    normalized_pref = [_norm_lang(lang) or lang for lang in preferred_languages]
    for pref in normalized_pref:
        for audio_order, stream in enumerate(media.audio_streams):
            if stream.language == pref:
                logger.info(
                    "Selected preferred audio track %d (global idx %d, lang=%s, codec=%s)",
                    audio_order, stream.index, stream.language, stream.codec,
                )
                return audio_order
    logger.info("No preferred language match (%s); using first audio track.", ",".join(normalized_pref))
    return 0


__all__ = [
    "MediaInfo",
    "AudioStream",
    "SubtitleStream",
    "StreamBase",
    "inspect_media",
    "choose_audio_track",
    "LANG_MAP",
    "_norm_lang",
]
