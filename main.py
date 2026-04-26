"""
Main subtitle generation pipeline.

This is the entry point for the anime subtitle pipeline. It orchestrates
all the components:
1. Audio extraction from video
2. Japanese ASR transcription
3. Japanese to English translation
4. Optional LLM polishing
5. SRT file generation
6. Optional subtitle muxing back into video
7. JSON logging

Usage:
    python main.py /path/to/video.mkv
    python main.py /path/to/video.mkv --no-llm
    python main.py /path/to/video.mkv --profile prod --no-mux
"""

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Optional

from config import Config, set_config
from audio_utils import (
    check_ffmpeg_available,
    extract_audio_with_ffmpeg,
    find_japanese_audio_track,  # retained for backward compatibility
    mux_subtitle_to_video
)
from core.artifacts.models import (
    ARTIFACT_TYPE_MKV,
    ARTIFACT_TYPE_SRT,
    PIPELINE_STATUS_COMPLETED,
    PIPELINE_STATUS_FAILED,
)
from core.artifacts.pipeline_wiring import compute_media_hash, open_registry
from media_inspect import inspect_media, choose_audio_track
from models import SubtitleCandidate
from asr import FasterWhisperASR, build_candidate_from_segments
from mt import translate_candidate_jp_to_en
from llm_polish import (
    polish_candidate_with_llm,
    enforce_constraints_on_candidate,
)
from srt_writer import write_candidate_srt
from tracing import setup_tracing, start_span


# Configure logging
def setup_logging(level: str = "INFO"):
    """
    Set up logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


logger = logging.getLogger(__name__)


def _emit_registry_run_id(registry_run_id: Optional[str]) -> None:
    """Log and print a stable registry run id for scripts and UI wrappers."""
    if not registry_run_id:
        logger.info("  Registry run: <not recorded>")
        return
    logger.info("  Registry run: %s", registry_run_id)
    print(f"registry_run_id={registry_run_id}")


def save_candidate_chain_log(asr_candidate: SubtitleCandidate, mt_candidate: SubtitleCandidate, final_candidate: SubtitleCandidate, output_path: str):
    """Save unified candidate processing chain to JSON.

    Structure:
    {
      "candidates": [
         { id, language, source, origin_stream, segment_count, meta, segments: [ {start,end,duration,text} ] },
         ...
      ],
      "final_candidate_id": "..."
    }
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def serialize_candidate(c: SubtitleCandidate) -> dict:
        return {
            "id": c.id,
            "language": c.language,
            "source": c.source,
            "origin_stream": c.origin_stream,
            "segment_count": len(c.segments),
            "meta": c.meta,
            "segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "duration": round(s.end - s.start, 3),
                    "text": s.text,
                }
                for s in c.segments
            ],
        }

    data = {
        "candidates": [
            serialize_candidate(asr_candidate),
            serialize_candidate(mt_candidate),
            serialize_candidate(final_candidate),
        ],
        "final_candidate_id": final_candidate.id,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved candidate chain log to {output_path.name}")


def process_video(
    video_path: str,
    config: Config,
    no_llm: bool = False,
    no_mux: bool = False,
    audio_track: Optional[int] = None,
    registry=None,
    media_hash: Optional[str] = None,
) -> dict:
    """
    Process a single video file through the complete pipeline.
    
    Args:
        video_path: Path to input video file
        config: Configuration object
        no_llm: Skip LLM polishing step
        no_mux: Skip muxing subtitles into video
        audio_track: Specific audio track index (None = auto-detect)
        registry: Optional ArtifactRegistry. If omitted, this function opens
            the configured registry itself and records best-effort lineage.
        media_hash: Optional SHA-256 of the input media. If omitted, this
            function computes it before opening the registry.
        
    Returns:
        Dictionary with output file paths and statistics
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    logger.info("=" * 70)
    logger.info(f"Processing: {video_path.name}")
    logger.info("=" * 70)
    
    # Prepare paths
    video_stem = video_path.stem
    outbox_dir = Path(config.get_path("outbox"))
    audio_path = Path(config.get_path("temp")) / f"{video_stem}.wav"
    srt_path = outbox_dir / f"{video_stem}.en.srt"
    raw_srt_path = outbox_dir / f"{video_stem}.raw.en.srt"
    log_path = Path(config.get_path("logs")) / f"{video_stem}.json"

    result = {
        "input_video": str(video_path),
        "audio_file": str(audio_path),
        "srt_file": str(srt_path),
        "raw_srt_file": str(raw_srt_path),
        "log_file": str(log_path),
        "muxed_video": None,
        "segment_count": 0,
        "success": False,
        "registry_run_id": None,
    }

    from orchestrator import (
        _reg_finish_run,
        _reg_start_run,
        _reg_store_artifact,
        _reg_store_candidate,
    )

    _registry_owned = registry is None
    if media_hash is None:
        try:
            media_hash = compute_media_hash(video_path)
            logger.debug("Media hash: %s", media_hash)
        except Exception as exc:
            logger.warning("Could not compute media hash -- registry disabled: %s", exc)

    if registry is None and media_hash is not None:
        registry = open_registry(config)

    if registry is not None and media_hash is not None:
        try:
            registry.upsert_media_asset(
                media_hash=media_hash,
                file_path=str(video_path),
                file_name=video_path.name,
            )
        except Exception as exc:
            logger.warning("ArtifactRegistry: failed to upsert media asset -- %s", exc)

    _run_id = uuid.uuid4().hex
    _run_db_id = _reg_start_run(registry, media_hash, config, run_id=_run_id)
    if registry is not None and _run_db_id is not None:
        result["registry_run_id"] = _run_id
    
    try:
        # ===================================================================
        # Step 1: Extract audio
        # ===================================================================
        logger.info("\n[1/6] Extracting audio track from video...")
        
        with start_span("extract_audio", video=str(video_path.name)):
            if audio_track is None:
                # New path: use media inspection for dynamic selection
                try:
                    media = inspect_media(str(video_path))
                    preferred = config.get("audio", "preferred_languages", default=["ja", "jpn", "ja-JP"])
                    audio_track = choose_audio_track(media, preferred_languages=preferred)
                except Exception as e:
                    logger.warning(f"Media inspection failed ({e}); falling back to legacy detection")
                    fallback = find_japanese_audio_track(str(video_path))
                    audio_track = fallback if fallback is not None else 0
            audio_path = extract_audio_with_ffmpeg(
                input_video_path=str(video_path),
                output_audio_path=str(audio_path),
                audio_track_index=audio_track
            )
        
        # ===================================================================
        # Step 2: Japanese ASR (Speech to Text, candidate-based)
        # ===================================================================
        logger.info("\n[2/6] Running Japanese ASR (Faster-Whisper)...")
        with start_span("asr_transcription", model=config.asr_model_name, profile=config.profile):
            asr = FasterWhisperASR(config)
            segments, _ = asr.transcribe_audio_to_segments(str(audio_path))
            # Build generic candidate reflecting selected audio track & detected language
            try:
                media_for_lang = inspect_media(str(video_path))
                audio_lang = None
                if audio_track is not None and audio_track < len(media_for_lang.audio_streams):
                    audio_lang = media_for_lang.audio_streams[audio_track].language or media_for_lang.audio_streams[audio_track].raw_language
            except Exception:
                audio_lang = None
            candidate_lang = audio_lang or config.asr_language or "und"
            asr_candidate = build_candidate_from_segments(
                segments,
                config,
                candidate_id=f"asr_{candidate_lang}",
                language=candidate_lang,
                origin_stream=f"audio:{audio_track if audio_track is not None else 0}",
            )
            result["asr_candidate_language"] = asr_candidate.language
            result["asr_candidate_origin_stream"] = asr_candidate.origin_stream
            result["asr_candidate_segment_count"] = asr_candidate.segment_count
            # TODO: restore asr.unload_model() — disabled due to crash after destructor in legacy path
            # asr.unload_model()
        _asr_db_id = _reg_store_candidate(
            registry,
            media_hash,
            asr_candidate,
            source="asr",
            model_version=config.asr_model_name,
        )
        
        if not asr_candidate.segments:
            logger.error("No speech segments detected in audio")
            _reg_finish_run(
                registry,
                _run_id,
                status=PIPELINE_STATUS_FAILED,
                error_message="No speech segments detected in audio",
            )
            return result
        
        logger.info(
            f"Transcribed {asr_candidate.segment_count} segments (audio track {audio_track}) "
            f"candidate_id={asr_candidate.id} origin={asr_candidate.origin_stream}"
        )
        
        # ===================================================================
        # Step 3: Japanese to English translation (candidate-based)
        # ===================================================================
        logger.info("\n[3/6] Translating Japanese to English (MarianMT, candidate model)...")
        with start_span("machine_translation", model=config.mt_model_name, device=config.mt_device):
            mt_candidate = translate_candidate_jp_to_en(asr_candidate, config)
        _mt_db_id = _reg_store_candidate(
            registry,
            media_hash,
            mt_candidate,
            source="mt",
            model_version=config.mt_model_name,
            parent_id=_asr_db_id,
        )
        
        # ===================================================================
        # Step 3.5: Write raw MT SRT (always, before optional LLM polish)
        # ===================================================================
        logger.info("\n[3.5/6] Writing raw MT SRT (pre-polish)...")
        with start_span("write_raw_srt", output=str(raw_srt_path)):
            write_candidate_srt(mt_candidate, str(raw_srt_path), config)
            logger.info(f"✓ Raw MT SRT written: {raw_srt_path.name}")
        _reg_store_artifact(
            registry,
            media_hash,
            ARTIFACT_TYPE_SRT,
            raw_srt_path,
            candidate_db_id=_mt_db_id,
            run_db_id=_run_db_id,
        )

        # ===================================================================
        # Step 4: Optional LLM polishing (candidate-based)
        # ===================================================================
        if no_llm or not config.llm_enabled:
            logger.info("\n[4/6] Skipping LLM polishing (disabled)")
            with start_span("llm_polish", enabled=False):
                final_candidate = mt_candidate  # pass-through
            _final_db_id = _mt_db_id
        else:
            logger.info("\n[4/6] Polishing subtitles with LLM (candidate model)...")
            with start_span("llm_polish", model=config.llm_model_name, base_url=config.llm_base_url):
                polished_candidate = polish_candidate_with_llm(mt_candidate, config)
                final_candidate = enforce_constraints_on_candidate(polished_candidate, config)
            _final_db_id = _reg_store_candidate(
                registry,
                media_hash,
                final_candidate,
                source="mt_llm",
                model_version=config.llm_model_name,
                parent_id=_mt_db_id,
            )
        
        # ===================================================================
        # Step 5: Write SRT file (candidate-based)
        # ===================================================================
        logger.info("\n[5/6] Writing SRT subtitle file (from final candidate)...")
        with start_span("write_srt", output=str(srt_path)):
            srt_path = write_candidate_srt(final_candidate, str(srt_path), config)
            logger.info(f"✓ SRT file created: {srt_path}")
        _reg_store_artifact(
            registry,
            media_hash,
            ARTIFACT_TYPE_SRT,
            srt_path,
            candidate_db_id=_final_db_id,
            run_db_id=_run_db_id,
        )
        
        # ===================================================================
        # Step 6: Optional muxing
        # ===================================================================
        if no_mux or not config.mux_enabled:
            logger.info("\n[6/6] Skipping video muxing (disabled)")
        else:
            logger.info("\n[6/6] Muxing subtitles into video...")
            with start_span("mux_subtitles"):
                suffix = config.mux_output_suffix
                muxed_path = outbox_dir / f"{video_stem}.{suffix}{video_path.suffix}"

                muxed_path = mux_subtitle_to_video(
                    input_video_path=str(video_path),
                    subtitle_path=str(srt_path),
                    output_video_path=str(muxed_path),
                    subtitle_language=config.get("mux", "subtitle_language", default="eng"),
                    subtitle_title=config.get("mux", "subtitle_title", default="English")
                )

                result["muxed_video"] = str(muxed_path)
                logger.info(f"✓ Muxed video created: {muxed_path}")

                _reg_store_artifact(
                    registry,
                    media_hash,
                    ARTIFACT_TYPE_MKV,
                    muxed_path,
                    candidate_db_id=_final_db_id,
                    run_db_id=_run_db_id,
                )
        
        # ===================================================================
        # Save candidate chain log
        # ===================================================================
        if config.get("logging", "save_segment_json", default=True):
            with start_span("save_segment_log", output=str(log_path)):
                save_candidate_chain_log(asr_candidate, mt_candidate, final_candidate, str(log_path))
        
        # Update result metadata
        result["segment_count"] = final_candidate.segment_count
        result["final_candidate_id"] = final_candidate.id
        
        # ===================================================================
        # Cleanup temp files
        # ===================================================================
        if audio_path.exists():
            audio_path.unlink()
            logger.debug(f"Cleaned up temp file: {audio_path.name}")
        
        result["success"] = True
        _reg_finish_run(registry, _run_id, status=PIPELINE_STATUS_COMPLETED)
        
        logger.info("\n" + "=" * 70)
        logger.info("✓ Processing complete!")
        logger.info(f"  SRT file: {srt_path}")
        if result["muxed_video"]:
            logger.info(f"  Video file: {result['muxed_video']}")
        logger.info("=" * 70)
        
        return result
        
    except Exception as e:
        logger.error(f"\n✗ Processing failed: {e}", exc_info=True)
        result["error"] = str(e)
        _reg_finish_run(
            registry,
            _run_id,
            status=PIPELINE_STATUS_FAILED,
            error_message=str(e),
        )
        return result
    finally:
        if _registry_owned and registry is not None:
            registry.close()


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Generate English subtitles for Japanese anime/video files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single video with default settings
  python main.py video.mkv
  
  # Use prod profile (4090 GPU) and skip LLM polishing
  python main.py video.mkv --profile prod --no-llm
  
  # Generate SRT only, don't mux into video
  python main.py video.mkv --no-mux
  
  # Use specific audio track
  python main.py video.mkv --audio-track 1
  
  # Use custom config file
  python main.py video.mkv --config my_config.yaml

  # List available audio & subtitle tracks without processing
  python main.py video.mkv --list-tracks

  # Extract all embedded English subtitle tracks for reference / training data
  python main.py video.mkv --extract-en-subs
        """
    )
    
    parser.add_argument(
        "video",
        type=str,
        help="Path to input video file (MKV, MP4, etc.)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to config file (default: config.yaml)"
    )
    
    parser.add_argument(
        "--profile",
        type=str,
        choices=["dev", "prod"],
        help="Override config profile (dev or prod)"
    )
    
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM polishing step (use raw MT output)"
    )
    
    parser.add_argument(
        "--no-mux",
        action="store_true",
        help="Don't mux subtitles into video (SRT only)"
    )
    
    parser.add_argument(
        "--audio-track",
        type=int,
        help="Specific audio track index to use (default: auto-detect Japanese)"
    )

    parser.add_argument(
        "--list-tracks",
        action="store_true",
        help="List audio/subtitle tracks and exit without processing"
    )

    parser.add_argument(
        "--extract-en-subs",
        action="store_true",
        help=(
            "Extract all embedded English text subtitle tracks to the outbox "
            "as <stem>.en.s<N>.srt files, then exit. Useful for collecting "
            "reference/training data from files that already have good EN subs."
        )
    )

    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help=(
            "In generate mode, inspect sources and report the planned strategy "
            "without running ASR, MT, LLM, QC, muxing, registry writes, or output writes"
        )
    )
    
    parser.add_argument(
        "--mode",
        type=str,
        choices=["subtitle", "generate", "benchmark"],
        default="generate",
        help=(
            "Run mode: 'generate' (production EN subs, default), "
            "'benchmark' (compare all candidate sources, writes benchmark_results.json), "
            "'subtitle' (legacy JP→EN pipeline)"
        )
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override logging level"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    try:
        config = Config(config_path=args.config, profile_override=args.profile)
        set_config(config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Please create a config.yaml file or specify --config", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Set up logging
    log_level = args.log_level or config.log_level
    setup_logging(log_level)
    
    # Initialize tracing (respect TRACING_ENABLED env var)
    setup_tracing(service_name="anime-subtitle-pipeline")
    
    logger.info(f"Anime Subtitle Pipeline v1.0")
    logger.info(f"Profile: {config.profile}")
    logger.info(f"Configuration loaded from: {config.config_path}")
    
    # Check ffmpeg availability
    if not check_ffmpeg_available():
        logger.error("ffmpeg not found in PATH")
        logger.error("Please install ffmpeg and ensure it's accessible")
        sys.exit(1)
    
    # Fast path: list tracks only
    if args.list_tracks:
        try:
            media = inspect_media(args.video)
        except Exception as e:
            logger.error(f"Failed to inspect media: {e}")
            sys.exit(1)

        logger.info("\nAvailable Audio Tracks (ffmpeg audio-order index -> global index):")
        if media.audio_streams:
            for audio_order, stream in enumerate(media.audio_streams):
                logger.info(
                    "  %d (global %d): codec=%s channels=%d rate=%dHz lang=%s",
                    audio_order,
                    stream.index,
                    stream.codec,
                    getattr(stream, "channels", 2),
                    getattr(stream, "sample_rate", 0),
                    stream.language or stream.raw_language or "-",
                )
        else:
            logger.info("  <none>")

        logger.info("\nAvailable Subtitle Tracks (global index):")
        if media.subtitle_streams:
            for sub_order, stream in enumerate(media.subtitle_streams):
                logger.info(
                    "  %d (global %d): codec=%s lang=%s bitmap=%s",
                    sub_order,
                    stream.index,
                    stream.codec,
                    stream.language or stream.raw_language or "-",
                    "yes" if stream.is_bitmap else "no",
                )
        else:
            logger.info("  <none>")

        logger.info("\nUse --audio-track <index> to select a specific audio track.")
        sys.exit(0)

    # --extract-en-subs: pull all embedded English text subtitle tracks to outbox,
    # then continue into the normal generation pipeline so you get both the
    # reference/embedded subs and the freshly-generated output for comparison.
    if args.extract_en_subs and not args.inspect_only:
        try:
            from subtitle_utils import extract_subtitle_track as _extract_sub
            _media_for_extract = inspect_media(args.video)
        except Exception as e:
            logger.error(f"Failed to inspect media for EN sub extraction: {e}")
            sys.exit(1)

        _video_path = Path(args.video)
        _outbox_dir = Path(config.get_path("outbox"))
        _outbox_dir.mkdir(parents=True, exist_ok=True)

        _en_text_streams = [
            s for s in _media_for_extract.subtitle_streams
            if not s.is_bitmap
            and (s.language or s.raw_language or "").strip().lower() in {"en", "eng", "en-us", "en-gb"}
        ]

        if not _en_text_streams:
            logger.info("No embedded English text subtitle tracks found; proceeding to generation.")
        else:
            logger.info(f"Found {len(_en_text_streams)} English text subtitle stream(s) — extracting before generation.")
            for stream in _en_text_streams:
                out_name = f"{_video_path.stem}.en.s{stream.index}.srt"
                out_path = _outbox_dir / out_name
                logger.info(f"  Extracting stream {stream.index} (codec={stream.codec}) → {out_name}")
                _temp_dir = Path(config.get_path("temp"))
                try:
                    _cand = _extract_sub(_video_path, stream.index, language="en",
                                         output_dir=_temp_dir)
                    write_candidate_srt(_cand, str(out_path), config)
                    # Remove intermediate demux SRT; outbox copy is the deliverable.
                    (_temp_dir / f"{_video_path.stem}.track{stream.index}.en.srt").unlink(missing_ok=True)
                    logger.info(f"  ✓ Written: {out_name}")
                except Exception as e:
                    logger.error(f"  ✗ Failed to extract stream {stream.index}: {e}")

        # Fall through — generation runs below regardless.

    # Dispatch to appropriate mode
    try:
        if args.mode == "benchmark":
            from benchmark import run_benchmark
            logger.info("Running in BENCHMARK mode (compare all candidate sources)")
            bm_registry = open_registry(config)
            results = run_benchmark(
                video_path=args.video,
                config=config,
                use_llm=not args.no_llm,
                registry=bm_registry,
            )
            logger.info("\nBenchmark Result:")
            logger.info(f"  Reference: {results['reference_id']}")
            logger.info(f"  Candidates: {len(results['candidates'])}")
            logger.info(f"  Comparisons: {len(results['comparisons'])}")
            logger.info(f"  Run ID: {results.get('run_id', '<none>')}")
            sys.exit(0)
        elif args.mode == "generate":
            from orchestrator import run_generate
            from core.artifacts.pipeline_wiring import compute_media_hash, open_registry
            logger.info("Running in GENERATE mode (strategy selection)")
            media = inspect_media(args.video)

            if args.inspect_only:
                logger.info("Inspect-only requested: registry and output writes disabled")
                registry = None
                media_hash = None
            else:
                # Compute media hash and open registry before generation so that
                # the pipeline run is recorded even if generation fails mid-way.
                video_path_for_hash = Path(args.video)
                try:
                    media_hash = compute_media_hash(video_path_for_hash)
                    logger.debug("Media hash: %s", media_hash)
                except Exception as exc:
                    logger.warning("Could not compute media hash -- registry disabled: %s", exc)
                    media_hash = None

                registry = open_registry(config)

            try:
                meta = run_generate(
                    media,
                    config,
                    no_llm=args.no_llm,
                    audio_track_override=args.audio_track,
                    skip_embedded_en=args.extract_en_subs,
                    registry=registry,
                    media_hash=media_hash,
                    inspect_only=args.inspect_only,
                )
            finally:
                if registry is not None:
                    registry.close()
            if args.inspect_only:
                logger.info("\nGenerate Inspect Result:")
                logger.info(f"  Planned strategy: {meta['strategy']}")
                logger.info(f"  Planned SRT: {meta['planned_output_srt']}")
                logger.info("  Execution: skipped")
            else:
                logger.info("\nGeneration Result:")
                logger.info(f"  Strategy: {meta['strategy']}")
                logger.info(f"  Candidate: {meta['candidate_id']}")
                logger.info(f"  Segments: {meta['segment_count']}")
                logger.info(f"  Output SRT: {meta['output_srt']}")
            routing = meta.get("routing_decision", {})
            decision = routing.get("decision", "")
            if decision:
                logger.info(f"  Routing: {decision.upper()}")
                for reason in routing.get("reasons", []):
                    logger.info(f"    • {reason}")
            _emit_registry_run_id(meta.get("registry_run_id"))
            sys.exit(0)
        else:  # legacy subtitle mode
            logger.info("Running in legacy SUBTITLE mode (JP audio → ASR → MT → LLM)")
            result = process_video(
                video_path=args.video,
                config=config,
                no_llm=args.no_llm,
                no_mux=args.no_mux,
                audio_track=args.audio_track,
            )
            if result["success"]:
                _emit_registry_run_id(result.get("registry_run_id"))
                sys.exit(0)
            else:
                logger.error("Processing failed")
                sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
