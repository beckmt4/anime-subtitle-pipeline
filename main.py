"""CLI entry point for generate, benchmark, and review workflows."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from core.extract.audio_utils import check_ffmpeg_available
from core.artifacts.pipeline_wiring import compute_media_hash, open_registry
from core.ocr import create_backend as create_ocr_backend
from core.runtime import Config, run_generate, set_config, setup_tracing
from core.media import inspect_media
from core.subtitles.srt_writer import write_candidate_srt


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
        "--source-language",
        type=str,
        default="auto",
        metavar="LANG",
        help=(
            "Override the audio source language for ASR (e.g. 'ja', 'en', 'zh'). "
            "When set, container metadata language tags are ignored and the specified "
            "language is used for transcription. Default: 'auto' (use container metadata "
            "and language probe)."
        ),
    )
    
    parser.add_argument(
        "--mode",
        type=str,
        choices=["subtitle", "generate", "benchmark", "review"],
        default="generate",
        help=(
            "Run mode: 'generate' (production EN subs, default), "
            "'benchmark' (compare all candidate sources, writes benchmark_results.json), "
            "'review' (local review queue and approval workflow), "
            "'subtitle' (deprecated alias of generate)"
        )
    )

    parser.add_argument(
        "--review-action",
        type=str,
        choices=["queue", "render", "approve"],
        default="queue",
        help="In review mode: queue (list tasks), render (build local HTML UI), approve (apply edits).",
    )
    parser.add_argument(
        "--task-id",
        type=int,
        help="In review mode: review task id for render/approve actions.",
    )
    parser.add_argument(
        "--compare-candidate-id",
        type=int,
        help="In review mode render action: optional candidate id for side-by-side comparison.",
    )
    parser.add_argument(
        "--review-ui-output",
        type=str,
        help="In review mode render action: output path for the local review UI HTML file.",
    )
    parser.add_argument(
        "--review-edits-json",
        type=str,
        help="In review mode approve action: path to JSON payload exported from the review UI.",
    )
    parser.add_argument(
        "--review-notes",
        type=str,
        help="In review mode approve action: reviewer notes to persist with approval.",
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override logging level"
    )

    parser.add_argument(
        "--strict-benchmark",
        action="store_true",
        dest="strict_benchmark",
        help=(
            "In benchmark mode, exit with code 2 when only one candidate is generated "
            "(i.e. no comparison was possible)."
        )
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
    
    logger.info("Anime Subtitle Pipeline v1.0")
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
            from core.extract.subtitle_utils import extract_subtitle_track as _extract_sub
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
        if args.mode == "review":
            from core.review import approve_review_task, list_review_queue, render_local_review_ui

            logger.info("Running in REVIEW mode")
            registry = open_registry(config)
            if registry is None:
                logger.error("Artifact registry unavailable; review mode requires a writable registry.")
                sys.exit(1)
            try:
                if args.review_action == "queue":
                    tasks = list_review_queue(registry)
                    if not tasks:
                        logger.info("No pending review tasks.")
                    for task in tasks:
                        logger.info(
                            "Task #%s media=%s candidate_id=%s status=%s",
                            task.id,
                            task.media_hash,
                            task.candidate_id,
                            task.status,
                        )
                elif args.review_action == "render":
                    if args.task_id is None:
                        logger.error("--task-id is required for --review-action render")
                        sys.exit(2)
                    ui_path = args.review_ui_output or str(
                        Path(config.get_path("outbox")) / f"review_task_{args.task_id}.html"
                    )
                    rendered = render_local_review_ui(
                        registry,
                        task_id=args.task_id,
                        output_path=ui_path,
                        compare_candidate_id=args.compare_candidate_id,
                    )
                    logger.info("Review UI written: %s", rendered)
                else:  # approve
                    if args.task_id is None:
                        logger.error("--task-id is required for --review-action approve")
                        sys.exit(2)
                    edits = {}
                    if args.review_edits_json:
                        edits = json.loads(Path(args.review_edits_json).read_text(encoding="utf-8"))
                    out_path = str(Path(config.get_path("outbox")) / f"review_task_{args.task_id}.approved.srt")
                    approved = approve_review_task(
                        registry,
                        task_id=args.task_id,
                        edited_segments=edits,
                        reviewer_notes=args.review_notes,
                        output_srt_path=out_path,
                    )
                    logger.info("Approved candidate id: %s", approved["approved_candidate_id"])
                    logger.info("Stored approved output: %s", approved["output_srt_path"])
            finally:
                registry.close()
            sys.exit(0)
        elif args.mode == "benchmark":
            from core.benchmark import run_benchmark
            logger.info("Running in BENCHMARK mode (compare all candidate sources)")
            ocr_backend = create_ocr_backend(config)
            if ocr_backend is None:
                logger.info("OCR backend not configured; bitmap subtitle OCR candidates will be skipped")
            else:
                logger.info("OCR backend active: %s", ocr_backend.__class__.__name__)
            bm_registry = open_registry(config)
            results = run_benchmark(
                video_path=args.video,
                config=config,
                use_llm=not args.no_llm,
                registry=bm_registry,
                ocr_backend=ocr_backend,
            )
            logger.info("\nBenchmark Result:")
            logger.info(f"  Reference: {results['reference_id']}")
            logger.info(f"  Candidates: {len(results['candidates'])}")
            logger.info(f"  Comparisons: {len(results['comparisons'])}")
            logger.info(f"  Run ID: {results.get('run_id', '<none>')}")
            if results.get("status") == "single_candidate_only":
                print(f"WARNING: {results.get('warning', 'Only one candidate — no comparison performed.')}")
                if getattr(args, "strict_benchmark", False):
                    sys.exit(2)
            sys.exit(0)
        elif args.mode in {"generate", "subtitle"}:
            if args.mode == "subtitle":
                logger.info("Running in SUBTITLE mode (alias of generate)")
            else:
                logger.info("Running in GENERATE mode (strategy selection)")
            media = inspect_media(args.video)
            ocr_backend = create_ocr_backend(config)
            if ocr_backend is None:
                logger.info("OCR backend not configured; bitmap subtitle OCR sources will be skipped")
            else:
                logger.info("OCR backend active: %s", ocr_backend.__class__.__name__)

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
                    source_language=args.source_language,
                    ocr_backend=ocr_backend,
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
            
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
