"""Benchmark orchestration for comparing subtitle generation methods.

This module provides run_benchmark() which:
1. Extracts embedded EN subtitle track as reference
2. Generates EN candidates from EN audio ASR and JP audio ASR+MT
3. Compares candidates against reference using metrics (WER, BLEU, chrF)
4. Saves results to benchmark_results.json
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from config import Config
from media_inspect import inspect_media, MediaInfo
from audio_utils import extract_audio_with_ffmpeg
from subtitle_utils import extract_subtitle_track
from asr import FasterWhisperASR, build_candidate_from_segments
from mt import translate_candidate_jp_to_en
from llm_polish import polish_candidate_with_llm, enforce_constraints_on_candidate
from models import SubtitleCandidate
from compare_core import compare_candidates
from tracing import start_span

logger = logging.getLogger(__name__)


def find_embedded_en_subtitle(media: MediaInfo) -> Optional[int]:
    """Find first English subtitle track (global stream index).
    
    Args:
        media: MediaInfo from inspect_media
        
    Returns:
        Global stream index of first EN subtitle, or None if not found
    """
    for stream in media.subtitle_streams:
        lang = (stream.language or stream.raw_language or "").lower()
        if lang in ["en", "eng", "en-us", "english"]:
            if not stream.is_bitmap:
                logger.info(f"Found EN subtitle stream: index={stream.index} lang={lang}")
                return stream.index
            else:
                logger.debug(f"Skipping bitmap subtitle stream {stream.index}")
    
    logger.warning("No text-based EN subtitle stream found")
    return None


def find_audio_track_by_language(media: MediaInfo, language_codes: list[str]) -> Optional[int]:
    """Find audio track order index matching any of the given language codes.
    
    Args:
        media: MediaInfo from inspect_media
        language_codes: List of language codes to match (e.g., ["en", "eng"])
        
    Returns:
        Audio track order index (0-based), or None if not found
    """
    lang_set = {code.lower() for code in language_codes}
    
    for audio_order, stream in enumerate(media.audio_streams):
        lang = (stream.language or stream.raw_language or "").lower()
        if lang in lang_set:
            logger.info(f"Found audio track for {language_codes}: order={audio_order} global={stream.index}")
            return audio_order
    
    logger.warning(f"No audio track found for languages: {language_codes}")
    return None


def run_benchmark(
    video_path: str,
    config: Config,
    use_llm: bool = True,
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Run benchmark comparing different EN subtitle generation methods.
    
    Workflow:
    1. Extract embedded EN subtitle → reference candidate
    2. Generate EN candidate from EN audio ASR
    3. Generate EN candidate from JP audio ASR → MT (→ LLM)
    4. Compare both candidates against reference
    5. Save results to JSON
    
    Args:
        video_path: Path to video file
        config: Configuration object
        use_llm: Whether to apply LLM polishing to JP→EN candidate
        output_dir: Output directory for results (default: config outbox)
        
    Returns:
        Dictionary with benchmark results
        
    Raises:
        FileNotFoundError: If video doesn't exist
        RuntimeError: If required tracks not found
    """
    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    
    logger.info("=" * 70)
    logger.info(f"BENCHMARK MODE: {video_path_obj.name}")
    logger.info("=" * 70)
    
    # Inspect media
    with start_span("inspect_media"):
        media = inspect_media(str(video_path_obj))
    
    # Find required tracks
    en_sub_index = find_embedded_en_subtitle(media)
    if en_sub_index is None:
        raise RuntimeError(
            "Benchmark requires embedded EN subtitle track as reference. "
            "No suitable track found."
        )
    
    en_audio_order = find_audio_track_by_language(media, ["en", "eng"])
    ja_audio_order = find_audio_track_by_language(media, ["ja", "jpn", "jp"])
    
    if en_audio_order is None:
        logger.warning("No EN audio track found; skipping EN ASR candidate")
    if ja_audio_order is None:
        logger.warning("No JP audio track found; skipping JP→EN candidate")
    
    if en_audio_order is None and ja_audio_order is None:
        raise RuntimeError(
            "Benchmark requires at least one audio track (EN or JP). "
            "None found."
        )
    
    # Setup paths
    video_stem = video_path_obj.stem
    temp_dir = Path(config.get_path("temp"))
    output_dir_obj = Path(output_dir or config.get_path("outbox"))
    output_dir_obj.mkdir(parents=True, exist_ok=True)
    
    results = {
        "video": str(video_path_obj.name),
        "reference": None,
        "candidates": [],
        "comparisons": [],
    }
    
    # ========================================================================
    # Step 1: Extract embedded EN subtitle (reference)
    # ========================================================================
    logger.info("\n[1/4] Extracting embedded EN subtitle (reference)...")
    with start_span("extract_reference_subtitle"):
        ref_candidate = extract_subtitle_track(
            str(video_path_obj),
            en_sub_index,
            language="en",
            output_dir=temp_dir
        )
    
    logger.info(
        f"Reference candidate: {ref_candidate.id} "
        f"({ref_candidate.segment_count} segments)"
    )
    results["reference"] = {
        "id": ref_candidate.id,
        "source": ref_candidate.source,
        "language": ref_candidate.language,
        "segment_count": ref_candidate.segment_count,
    }
    
    # ========================================================================
    # Step 2: Generate EN candidate from EN audio ASR
    # ========================================================================
    en_asr_candidate = None
    if en_audio_order is not None:
        logger.info("\n[2/4] Generating EN candidate from EN audio ASR...")
        
        en_audio_path = temp_dir / f"{video_stem}_en.wav"
        with start_span("extract_en_audio"):
            extract_audio_with_ffmpeg(
                str(video_path_obj),
                str(en_audio_path),
                en_audio_order
            )
        
        with start_span("asr_en_audio", language="en"):
            asr = FasterWhisperASR(config)
            segments = asr.transcribe_audio_to_segments(
                str(en_audio_path),
                language="en"
            )
            en_asr_candidate = build_candidate_from_segments(
                segments,
                config,
                candidate_id="en_audio_asr",
                language="en",
                origin_stream=f"audio:{en_audio_order}"
            )
        
        logger.info(
            f"EN ASR candidate: {en_asr_candidate.id} "
            f"({en_asr_candidate.segment_count} segments)"
        )
        results["candidates"].append({
            "id": en_asr_candidate.id,
            "source": "asr",
            "language": "en",
            "segment_count": en_asr_candidate.segment_count,
        })
        
        # Cleanup
        if en_audio_path.exists():
            en_audio_path.unlink()
    
    # ========================================================================
    # Step 3: Generate EN candidate from JP audio ASR → MT (→ LLM)
    # ========================================================================
    ja_mt_candidate = None
    if ja_audio_order is not None:
        logger.info("\n[3/4] Generating EN candidate from JP audio ASR → MT...")
        
        ja_audio_path = temp_dir / f"{video_stem}_ja.wav"
        with start_span("extract_ja_audio"):
            extract_audio_with_ffmpeg(
                str(video_path_obj),
                str(ja_audio_path),
                ja_audio_order
            )
        
        # ASR (Japanese)
        with start_span("asr_ja_audio", language="ja"):
            asr = FasterWhisperASR(config)
            segments = asr.transcribe_audio_to_segments(
                str(ja_audio_path),
                language="ja"
            )
            ja_asr_candidate = build_candidate_from_segments(
                segments,
                config,
                candidate_id="ja_audio_asr",
                language="ja",
                origin_stream=f"audio:{ja_audio_order}"
            )
        
        # MT (Japanese → English)
        with start_span("mt_ja_to_en"):
            mt_candidate = translate_candidate_jp_to_en(ja_asr_candidate, config)
        
        # Optional LLM polishing
        if use_llm and config.llm_enabled:
            logger.info("Applying LLM polishing to JP→EN candidate...")
            with start_span("llm_polish_ja_mt"):
                polished = polish_candidate_with_llm(mt_candidate, config)
                ja_mt_candidate = enforce_constraints_on_candidate(polished, config)
            source_desc = "asr_mt_llm"
        else:
            logger.info("Skipping LLM polishing")
            ja_mt_candidate = mt_candidate
            source_desc = "asr_mt"
        
        logger.info(
            f"JP→EN candidate: {ja_mt_candidate.id} "
            f"({ja_mt_candidate.segment_count} segments)"
        )
        results["candidates"].append({
            "id": ja_mt_candidate.id,
            "source": source_desc,
            "language": "en",
            "segment_count": ja_mt_candidate.segment_count,
        })
        
        # Cleanup
        if ja_audio_path.exists():
            ja_audio_path.unlink()
    
    # ========================================================================
    # Step 4: Compare candidates against reference
    # ========================================================================
    logger.info("\n[4/4] Comparing candidates against reference...")
    
    if en_asr_candidate:
        with start_span("compare_en_asr"):
            comparison = compare_candidates(ref_candidate, en_asr_candidate)
            results["comparisons"].append(comparison)
            logger.info(
                f"EN ASR vs Reference: "
                f"WER={comparison['metrics']['wer']:.2%}, "
                f"BLEU={comparison['metrics']['bleu']:.1f}"
            )
    
    if ja_mt_candidate:
        with start_span("compare_ja_mt"):
            comparison = compare_candidates(ref_candidate, ja_mt_candidate)
            results["comparisons"].append(comparison)
            logger.info(
                f"JP→EN vs Reference: "
                f"WER={comparison['metrics']['wer']:.2%}, "
                f"BLEU={comparison['metrics']['bleu']:.1f}"
            )
    
    # ========================================================================
    # Save results
    # ========================================================================
    output_path = output_dir_obj / "benchmark_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n✓ Benchmark results saved: {output_path}")
    logger.info("=" * 70)
    
    return results


__all__ = ["run_benchmark"]
