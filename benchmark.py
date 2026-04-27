"""Benchmark orchestration for comparing subtitle generation methods.

This module provides generalized run_benchmark() which:
1. Discovers all JP/EN audio and subtitle tracks
2. Generates EN candidates from all available sources
3. Selects appropriate reference candidate
4. Performs pairwise comparisons with configurable metrics
5. Saves comprehensive results to benchmark_results.json and an HTML report
6. Persists each comparison as a BenchmarkRunRecord via ArtifactRegistry
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

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


def find_all_tracks_by_language(
    media: MediaInfo,
    track_type: str,
    language_codes: List[str]
) -> List[Tuple[int, int, str]]:
    """Find all tracks of given type matching any language code.

    Returns:
        List of (order_index, global_index, detected_language) tuples.
        order_index is used for ffmpeg -map; global_index is the stream index
        from the container.
    """
    lang_set = {code.lower() for code in language_codes}
    matches = []

    if track_type == "audio":
        streams = media.audio_streams
    elif track_type == "subtitle":
        streams = media.subtitle_streams
    else:
        return []

    for order_idx, stream in enumerate(streams):
        lang = (stream.language or stream.raw_language or "und").lower()
        if lang in lang_set:
            if track_type == "subtitle" and stream.is_bitmap:
                logger.debug("Skipping bitmap subtitle stream %d", stream.index)
                continue
            matches.append((order_idx, stream.index, lang))
            logger.info(
                "Found %s track: order=%d global=%d lang=%s",
                track_type, order_idx, stream.index, lang,
            )

    return matches


def select_reference_candidate(
    candidates: List[SubtitleCandidate],
    config: Config,
) -> Optional[SubtitleCandidate]:
    """Select reference candidate based on priority configuration."""
    if not candidates:
        return None

    from core.benchmark.config import BenchmarkConfig
    priority = BenchmarkConfig.from_config(config).reference_priority

    for pref in priority:
        for cand in candidates:
            if pref in cand.id:
                logger.info("Selected reference candidate: %s (priority: %s)", cand.id, pref)
                return cand

    logger.warning("No priority match; using first candidate: %s", candidates[0].id)
    return candidates[0]


def run_benchmark(
    video_path: str,
    config: Config,
    use_llm: bool = True,
    output_dir: Optional[str] = None,
    registry=None,
) -> Dict[str, Any]:
    """Run generalized benchmark comparing all available EN subtitle sources.

    Workflow:
    1. Discover all JP/EN audio and subtitle tracks
    2. Generate EN candidates from all enabled sources
    3. Select reference candidate based on priority
    4. Compare all candidates against reference (or pairwise if configured)
    5. Build per-candidate scorecards
    6. Save comprehensive results to JSON and HTML report
    7. Persist each comparison via ArtifactRegistry (if registry provided)

    Args:
        video_path: Path to video file.
        config: Loaded Config.
        use_llm: Whether to apply LLM polishing to MT candidates.
        output_dir: Output directory for results (default: config outbox).
        registry: Optional ArtifactRegistry instance.  When provided, each
            pairwise comparison is persisted as a BenchmarkRunRecord.

    Returns:
        Dictionary with comprehensive benchmark results including ``scorecards``.

    Raises:
        FileNotFoundError: If video doesn't exist.
        RuntimeError: If no suitable tracks found.
    """
    from core.benchmark.config import BenchmarkConfig
    bc = BenchmarkConfig.from_config(config)

    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    logger.info("=" * 70)
    logger.info("BENCHMARK MODE: %s", video_path_obj.name)
    logger.info("=" * 70)

    with start_span("inspect_media"):
        media = inspect_media(str(video_path_obj))

    translation_engines = bc.translation_engines

    logger.info("\n[Discovery Phase] Finding all JP/EN audio and subtitle tracks...")

    en_audio_tracks = find_all_tracks_by_language(media, "audio", ["en", "eng", "en-us"]) if bc.use_en_audio else []
    ja_audio_tracks = find_all_tracks_by_language(media, "audio", ["ja", "jpn", "jp", "ja-jp"]) if bc.use_ja_audio else []
    en_sub_tracks = find_all_tracks_by_language(media, "subtitle", ["en", "eng", "en-us"]) if bc.use_embedded_en else []
    ja_sub_tracks = find_all_tracks_by_language(media, "subtitle", ["ja", "jpn", "jp", "ja-jp"]) if bc.use_embedded_jp else []

    logger.info("  EN audio tracks: %d", len(en_audio_tracks))
    logger.info("  JP audio tracks: %d", len(ja_audio_tracks))
    logger.info("  EN subtitle tracks: %d", len(en_sub_tracks))
    logger.info("  JP subtitle tracks: %d", len(ja_sub_tracks))

    if not any([en_audio_tracks, ja_audio_tracks, en_sub_tracks, ja_sub_tracks]):
        raise RuntimeError(
            "No suitable tracks found for benchmarking. "
            "Video must have at least one EN or JP audio/subtitle track."
        )

    video_stem = video_path_obj.stem
    temp_dir = Path(config.get_path("temp"))
    output_dir_obj = Path(output_dir or config.get_path("outbox"))
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    candidates: List[SubtitleCandidate] = []
    candidate_metadata: List[Dict[str, Any]] = []

    logger.info("\n[Generation Phase] Generating EN candidates from all sources...")

    # 1. Embedded EN subtitles
    for idx, (order, global_idx, lang) in enumerate(en_sub_tracks):
        logger.info("\n[EN-sub %d] Extracting embedded EN subtitle (order=%d, global=%d)...", idx + 1, order, global_idx)
        with start_span("extract_embedded_en"):
            cand = extract_subtitle_track(
                str(video_path_obj),
                global_idx,
                language="en",
                output_dir=temp_dir,
            )
        candidates.append(cand)
        candidate_metadata.append({
            "id": cand.id,
            "source": "embedded",
            "language": "en",
            "origin_stream": cand.origin_stream,
            "segment_count": cand.segment_count,
        })
        logger.info("  → %s: %d segments", cand.id, cand.segment_count)

    # 2. Embedded JP subtitles → translation engine(s) → EN
    for idx, (order, global_idx, lang) in enumerate(ja_sub_tracks):
        logger.info("\n[JP-sub %d] Extracting embedded JP subtitle (order=%d, global=%d)...", idx + 1, order, global_idx)
        with start_span("extract_embedded_jp"):
            ja_cand = extract_subtitle_track(
                str(video_path_obj),
                global_idx,
                language="ja",
                output_dir=temp_dir,
            )
        for engine in translation_engines:
            logger.info("  Translating JP subtitle candidate with engine=%s", engine)
            with start_span("mt_embedded_jp", engine=engine):
                mt_cand = translate_candidate_jp_to_en(ja_cand, config, engine=engine)
            if use_llm and config.llm_enabled:
                with start_span("llm_polish_embedded_jp"):
                    polished = polish_candidate_with_llm(mt_cand, config)
                    final_cand = enforce_constraints_on_candidate(polished, config)
                source_desc = f"embedded_mt_{engine}_llm"
            else:
                final_cand = mt_cand
                source_desc = f"embedded_mt_{engine}"
            candidates.append(final_cand)
            candidate_metadata.append({
                "id": final_cand.id,
                "source": source_desc,
                "language": "en",
                "origin_stream": final_cand.origin_stream,
                "segment_count": final_cand.segment_count,
                "translation_engine": final_cand.meta.get("translation_engine", engine),
                "translation_model": final_cand.meta.get("translation_model") or final_cand.meta.get("model"),
                "translation_mode": final_cand.meta.get("translation_mode"),
                "translation_fallback": final_cand.meta.get("translation_fallback", False),
            })
            logger.info("  → %s: %d segments", final_cand.id, final_cand.segment_count)

    # 3. EN audio → ASR
    for idx, (order, global_idx, lang) in enumerate(en_audio_tracks):
        logger.info("\n[EN-audio %d] Generating EN candidate from EN audio ASR (order=%d)...", idx + 1, order)
        en_audio_path = temp_dir / f"{video_stem}_en_a{order}.wav"
        with start_span("extract_en_audio"):
            extract_audio_with_ffmpeg(str(video_path_obj), str(en_audio_path), order)
        with start_span("asr_en_audio", language="en"):
            asr = FasterWhisperASR(config)
            segments, _ = asr.transcribe_audio_to_segments(str(en_audio_path), language="en")
            cand = build_candidate_from_segments(
                segments,
                config,
                candidate_id=f"en_audio_asr_a{order}",
                language="en",
                origin_stream=f"audio:{order}",
            )
        candidates.append(cand)
        candidate_metadata.append({
            "id": cand.id,
            "source": "asr",
            "language": "en",
            "origin_stream": cand.origin_stream,
            "segment_count": cand.segment_count,
        })
        logger.info("  → %s: %d segments", cand.id, cand.segment_count)
        if en_audio_path.exists():
            en_audio_path.unlink()

    # 4. JP audio → ASR → translation engine(s) → EN
    for idx, (order, global_idx, lang) in enumerate(ja_audio_tracks):
        logger.info("\n[JP-audio %d] Generating EN candidate from JP audio ASR → MT (order=%d)...", idx + 1, order)
        ja_audio_path = temp_dir / f"{video_stem}_ja_a{order}.wav"
        with start_span("extract_ja_audio"):
            extract_audio_with_ffmpeg(str(video_path_obj), str(ja_audio_path), order)
        with start_span("asr_ja_audio", language="ja"):
            asr = FasterWhisperASR(config)
            segments, _ = asr.transcribe_audio_to_segments(str(ja_audio_path), language="ja")
            ja_asr_candidate = build_candidate_from_segments(
                segments,
                config,
                candidate_id=f"ja_audio_asr_a{order}",
                language="ja",
                origin_stream=f"audio:{order}",
            )
        for engine in translation_engines:
            logger.info("  Translating JP audio candidate with engine=%s", engine)
            with start_span("mt_ja_audio", engine=engine):
                mt_cand = translate_candidate_jp_to_en(ja_asr_candidate, config, engine=engine)
            if use_llm and config.llm_enabled:
                with start_span("llm_polish_ja_audio"):
                    polished = polish_candidate_with_llm(mt_cand, config)
                    final_cand = enforce_constraints_on_candidate(polished, config)
                source_desc = f"asr_mt_{engine}_llm"
            else:
                final_cand = mt_cand
                source_desc = f"asr_mt_{engine}"
            candidates.append(final_cand)
            candidate_metadata.append({
                "id": final_cand.id,
                "source": source_desc,
                "language": "en",
                "origin_stream": final_cand.origin_stream,
                "segment_count": final_cand.segment_count,
                "translation_engine": final_cand.meta.get("translation_engine", engine),
                "translation_model": final_cand.meta.get("translation_model") or final_cand.meta.get("model"),
                "translation_mode": final_cand.meta.get("translation_mode"),
                "translation_fallback": final_cand.meta.get("translation_fallback", False),
            })
            logger.info("  → %s: %d segments", final_cand.id, final_cand.segment_count)
        if ja_audio_path.exists():
            ja_audio_path.unlink()

    logger.info("\n[Comparison Phase] Generated %d EN candidates total", len(candidates))

    if not candidates:
        raise RuntimeError("No EN candidates generated; cannot perform benchmark")

    ref_candidate = select_reference_candidate(candidates, config)

    # Unique run_id for this benchmark session
    session_run_id = str(uuid.uuid4())

    _single_candidate = len(candidates) == 1

    results: Dict[str, Any] = {
        "video": str(video_path_obj.name),
        "reference_id": ref_candidate.id,
        "candidates": candidate_metadata,
        "comparisons": [],
        "run_id": session_run_id,
        "status": "single_candidate_only" if _single_candidate else "ok",
    }

    if _single_candidate:
        _warn_msg = (
            "Only one candidate was generated — no benchmark comparison is possible. "
            "Add more audio/subtitle tracks or enable additional translation engines."
        )
        logger.warning("⚠ BENCHMARK WARNING: %s", _warn_msg)
        results["warning"] = _warn_msg

    def _persist_comparison(comp: Dict[str, Any]) -> None:
        """Persist one comparison to the registry; silently skips if unavailable."""
        if registry is None:
            return
        if comp.get("ref_id") == comp.get("cand_id"):
            logger.warning(
                "Skipping self-comparison for candidate %r",
                comp.get("ref_id"),
            )
            return
        try:
            from core.artifacts.models import BenchmarkRunRecord
            metrics = comp.get("metrics", {})
            # Include num_segments so registry segment count matches the comparison result
            stored_metrics = {**metrics, "num_segments": comp.get("num_segments", 0)}
            # Use "|" as delimiter — candidate IDs use ":" for stream refs (e.g. "sub:10")
            registry.record_benchmark_run(BenchmarkRunRecord(
                media_hash=_media_hash,
                run_id=f"{session_run_id}|{comp['ref_id']}|{comp['cand_id']}",
                metrics=stored_metrics,
                wer=metrics.get("wer"),
                bleu=metrics.get("bleu"),
                chrf=metrics.get("chrf"),
            ))
        except Exception as exc:
            logger.warning("ArtifactRegistry: failed to persist benchmark run — %s", exc)

    # Derive a stable media hash for registry records (hex digest of path if real file)
    _media_hash = ""
    if registry is not None:
        try:
            from core.artifacts.pipeline_wiring import compute_media_hash
            _media_hash = compute_media_hash(video_path_obj)
        except Exception:
            _media_hash = video_path_obj.name  # fallback: filename as pseudo-hash

    if not _single_candidate:
        for cand in candidates:
            if cand.id == ref_candidate.id:
                continue
            logger.info("\nComparing %s vs %s...", cand.id, ref_candidate.id)
            with start_span("compare_candidate", cand_id=cand.id):
                comparison = compare_candidates(ref_candidate, cand, diff_threshold=5)
                comparison["diffs"] = comparison["diffs"][:bc.max_diffs_per_comparison]
                results["comparisons"].append(comparison)
                metrics = comparison["metrics"]
                logger.info(
                    "  WER=%.2f%%, BLEU=%.1f, chrF=%.1f, diffs=%d",
                    metrics["wer"] * 100, metrics["bleu"], metrics["chrf"],
                    comparison["num_diffs"],
                )
                _persist_comparison(comparison)

    if not _single_candidate and bc.compare_all_pairs and len(candidates) > 2:
        logger.info("\nComputing full pairwise comparison matrix...")
        for i, cand1 in enumerate(candidates):
            for j, cand2 in enumerate(candidates):
                if i >= j:
                    continue
                if cand1.id == cand2.id:
                    logger.warning("Skipping self-comparison: %s", cand1.id)
                    continue
                logger.info("\nComparing %s vs %s...", cand1.id, cand2.id)
                with start_span("compare_pair", cand1=cand1.id, cand2=cand2.id):
                    comparison = compare_candidates(cand1, cand2, diff_threshold=5)
                    comparison["diffs"] = comparison["diffs"][:bc.max_diffs_per_comparison]
                    results["comparisons"].append(comparison)
                    metrics = comparison["metrics"]
                    logger.info(
                        "  WER=%.2f%%, BLEU=%.1f, chrF=%.1f",
                        metrics["wer"] * 100, metrics["bleu"], metrics["chrf"],
                    )
                    _persist_comparison(comparison)

    # Build per-candidate scorecards and attach to results
    from core.benchmark.html_report import build_scorecards, render_html_report
    results["scorecards"] = build_scorecards(results)

    if not results["comparisons"]:
        logger.warning(
            "⚠ No comparisons produced for %s — "
            "only one candidate was generated or all non-reference candidates were skipped.",
            video_path_obj.name,
        )
        results["warning"] = (
            "No comparisons produced: only one candidate available or all candidates "
            "matched the reference and were skipped."
        )

    output_path = output_dir_obj / "benchmark_results.json"
    _tmp_json = output_path.parent / (output_path.name + ".tmp")
    try:
        with open(_tmp_json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        os.replace(_tmp_json, output_path)
    except Exception:
        _tmp_json.unlink(missing_ok=True)
        raise

    # Write HTML report alongside the JSON
    html_output_path = output_dir_obj / "benchmark_report.html"
    try:
        render_html_report(results, str(html_output_path))
        logger.info("✓ HTML report saved: %s", html_output_path)
    except Exception as exc:
        logger.warning("HTML report generation failed: %s", exc)

    logger.info("\n✓ Benchmark results saved: %s", output_path)
    logger.info("✓ Reference: %s", ref_candidate.id)
    logger.info("✓ Candidates: %d", len(candidates))
    logger.info("✓ Comparisons: %d", len(results["comparisons"]))
    logger.info("=" * 70)

    return results


__all__ = ["run_benchmark"]
