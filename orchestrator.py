"""High-level orchestration for generation and benchmarking modes.

Provides two primary flows:
- run_generate(media: MediaInfo, cfg: Config) -> dict
- run_benchmark(media: MediaInfo, cfg: Config) -> dict (wrapper around benchmark.run_benchmark)

Generation strategy decision tree (default priorities):
1. If prefer_subtitles and English text subtitles exist → use embedded EN
2. Else if English audio exists and preferred language is EN → EN audio ASR
3. Else if Japanese subtitles exist → JP subtitles → MT (→ optional LLM)
4. Else if Japanese audio exists → JP audio ASR → MT (→ optional LLM)
5. Else fallback to any available audio (EN or JP) → appropriate path

Config overrides (config.yaml generate section):
  generate:
    prefer_subtitles: true
    prefer_audio_language: "auto"  # "en" | "ja" | "auto"
    use_llm_polish: true

Returned metadata includes chosen strategy and output SRT path.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any

from config import Config
from media_inspect import MediaInfo
from subtitle_utils import extract_subtitle_track
from audio_utils import extract_audio_with_ffmpeg
from asr import FasterWhisperASR, build_candidate_from_segments
from mt import translate_candidate_jp_to_en
from llm_polish import polish_candidate_with_llm, enforce_constraints_on_candidate
from srt_writer import write_candidate_srt
from models import SubtitleCandidate
from tracing import start_span
from benchmark import run_benchmark as _core_benchmark

logger = logging.getLogger(__name__)


def _first_text_sub(media: MediaInfo, lang: str) -> int | None:
    for s in media.subtitle_streams:
        if s.is_bitmap:
            continue
        if (s.language or s.raw_language) == lang:
            return s.index
    return None


def _first_audio_order(media: MediaInfo, lang: str) -> int | None:
    for order, stream in enumerate(media.audio_streams):
        if (stream.language or stream.raw_language) == lang:
            return order
    return None


def run_generate(media: MediaInfo, cfg: Config) -> Dict[str, Any]:
    """Production generation flow selecting best available source for EN subtitles.

    Returns a metadata dict containing strategy, candidate info, and output paths.
    """
    video_path = media.path
    prefer_subtitles = cfg.get("generate", "prefer_subtitles", default=True)
    prefer_audio_language = cfg.get("generate", "prefer_audio_language", default="auto")
    use_llm_polish = cfg.get("generate", "use_llm_polish", default=True) and cfg.llm_enabled

    logger.info("=" * 70)
    logger.info(f"GENERATE MODE: {video_path.name}")
    logger.info("=" * 70)

    # Detect available sources
    en_sub_idx = _first_text_sub(media, "en")
    ja_sub_idx = _first_text_sub(media, "ja")
    en_audio_order = _first_audio_order(media, "en")
    ja_audio_order = _first_audio_order(media, "ja")

    logger.info(
        f"Sources detected: en_sub={en_sub_idx} ja_sub={ja_sub_idx} en_audio={en_audio_order} ja_audio={ja_audio_order}"
    )

    strategy = None
    candidate: SubtitleCandidate | None = None

    # Decision tree
    if prefer_subtitles and en_sub_idx is not None:
        strategy = "embedded_en"
        logger.info("Strategy: Use embedded English subtitles")
        with start_span("extract_embedded_en"):
            candidate = extract_subtitle_track(video_path, en_sub_idx, language="en")
    elif prefer_audio_language == "en" and en_audio_order is not None:
        strategy = "en_audio_asr"
        logger.info("Strategy: English audio ASR")
        with start_span("extract_en_audio"):
            audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_en_a{en_audio_order}.wav"
            extract_audio_with_ffmpeg(str(video_path), str(audio_path), en_audio_order)
        with start_span("asr_en_audio"):
            asr = FasterWhisperASR(cfg)
            segments = asr.transcribe_audio_to_segments(str(audio_path), language="en")
            candidate = build_candidate_from_segments(
                segments,
                cfg,
                candidate_id=f"en_audio_asr_a{en_audio_order}",
                language="en",
                origin_stream=f"audio:{en_audio_order}",
            )
    elif ja_sub_idx is not None:
        strategy = "embedded_jp_mt"
        logger.info("Strategy: Japanese subtitles → MT → EN")
        with start_span("extract_embedded_jp"):
            ja_candidate = extract_subtitle_track(video_path, ja_sub_idx, language="ja")
        with start_span("mt_embedded_jp"):
            mt_candidate = translate_candidate_jp_to_en(ja_candidate, cfg)
        if use_llm_polish:
            with start_span("llm_polish_embedded_jp"):
                polished = polish_candidate_with_llm(mt_candidate, cfg)
                candidate = enforce_constraints_on_candidate(polished, cfg)
            candidate.id = candidate.id + "_llm"
        else:
            candidate = mt_candidate
    elif (prefer_audio_language in ["ja", "auto"] and ja_audio_order is not None):
        strategy = "ja_audio_asr_mt"
        logger.info("Strategy: Japanese audio → ASR → MT → EN")
        with start_span("extract_ja_audio"):
            audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_ja_a{ja_audio_order}.wav"
            extract_audio_with_ffmpeg(str(video_path), str(audio_path), ja_audio_order)
        with start_span("asr_ja_audio"):
            asr = FasterWhisperASR(cfg)
            segments = asr.transcribe_audio_to_segments(str(audio_path), language="ja")
            ja_asr_candidate = build_candidate_from_segments(
                segments,
                cfg,
                candidate_id=f"ja_audio_asr_a{ja_audio_order}",
                language="ja",
                origin_stream=f"audio:{ja_audio_order}",
            )
        with start_span("mt_ja_audio"):
            mt_candidate = translate_candidate_jp_to_en(ja_asr_candidate, cfg)
        if use_llm_polish:
            with start_span("llm_polish_ja_audio"):
                polished = polish_candidate_with_llm(mt_candidate, cfg)
                candidate = enforce_constraints_on_candidate(polished, cfg)
            candidate.id = candidate.id + "_llm"
        else:
            candidate = mt_candidate
    elif en_audio_order is not None:  # fallback
        strategy = "en_audio_asr"
        logger.info("Fallback: English audio ASR")
        with start_span("extract_en_audio"):
            audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_en_a{en_audio_order}.wav"
            extract_audio_with_ffmpeg(str(video_path), str(audio_path), en_audio_order)
        with start_span("asr_en_audio"):
            asr = FasterWhisperASR(cfg)
            segments = asr.transcribe_audio_to_segments(str(audio_path), language="en")
            candidate = build_candidate_from_segments(
                segments,
                cfg,
                candidate_id=f"en_audio_asr_a{en_audio_order}",
                language="en",
                origin_stream=f"audio:{en_audio_order}",
            )
    else:
        raise RuntimeError("No usable source found for English subtitle generation")

    assert candidate is not None, "Generation strategy produced no candidate"

    # Write SRT
    out_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.en.srt"
    with start_span("write_final_srt"):
        write_candidate_srt(candidate, str(out_srt), cfg)

    metadata = {
        "video": str(video_path.name),
        "strategy": strategy,
        "candidate_id": candidate.id,
        "segment_count": candidate.segment_count,
        "output_srt": str(out_srt),
    }
    logger.info(f"✓ Generation complete (strategy={strategy}, segments={candidate.segment_count})")
    return metadata


def run_benchmark(media: MediaInfo, cfg: Config) -> Dict[str, Any]:
    """Wrapper to retain signature while delegating to existing benchmark logic."""
    with start_span("benchmark_wrapper"):
        return _core_benchmark(str(media.path), cfg, use_llm=cfg.get("generate", "use_llm_polish", default=True))

__all__ = ["run_generate", "run_benchmark"]
