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
from pathlib import Path
from typing import List, Optional

from config import Config, set_config
from audio_utils import (
    check_ffmpeg_available,
    extract_audio_with_ffmpeg,
    find_japanese_audio_track,  # retained for backward compatibility
    mux_subtitle_to_video
)
from media_inspect import inspect_media, choose_audio_track
from asr import FasterWhisperASR, Segment
from mt import MarianTranslator
from llm_polish import polish_english_subtitles_with_llm, enforce_subtitle_constraints_on_segments
from srt_writer import write_srt_file
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


def save_segment_log(segments: List[Segment], output_path: str):
    """
    Save detailed segment data to JSON file.
    
    Args:
        segments: List of segments to save
        output_path: Path for JSON output file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = []
    for seg in segments:
        data.append({
            "start": seg.start,
            "end": seg.end,
            "duration": seg.duration,
            "text_ja": seg.text_ja,
            "text_en_raw": seg.text_en_raw,
            "text_en_final": seg.text_en_final
        })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved segment log to {output_path.name}")


def _extract_audio_step(video_path: Path, audio_path: Path, audio_track: Optional[int]) -> Path:
    """Extract audio from video."""
    logger.info("\n[1/6] Extracting audio track from video...")
    with start_span("extract_audio", video=str(video_path.name)):
        if audio_track is None:
            audio_track = find_japanese_audio_track(str(video_path)) or 0
        return extract_audio_with_ffmpeg(str(video_path), str(audio_path), audio_track)


def _transcribe_audio_step(audio_path: Path, config: Config) -> List[Segment]:
    """Transcribe audio to Japanese text."""
    logger.info("\n[2/6] Running Japanese ASR (Faster-Whisper)...")
    with start_span("asr_transcription", model=config.asr_model_name, profile=config.profile):
        asr = FasterWhisperASR(config)
        return asr.transcribe_audio_to_segments(str(audio_path))


def _translate_segments_step(segments: List[Segment], config: Config) -> List[Segment]:
    """Translate Japanese segments to English."""
    logger.info("\n[3/6] Translating Japanese to English (MarianMT)...")
    with start_span("machine_translation", model=config.mt_model_name, device=config.mt_device):
        translator = MarianTranslator(config)
        segments = translator.translate_segments_ja_to_en(segments)
        translator.unload_model()
        return segments


def _polish_segments_step(segments: List[Segment], config: Config, no_llm: bool) -> List[Segment]:
    """Polish English translations with LLM."""
    if no_llm or not config.llm_enabled:
        logger.info("\n[4/6] Skipping LLM polishing (disabled)")
        with start_span("llm_polish", enabled=False):
            for seg in segments:
                seg.text_en_final = seg.text_en_raw
    else:
        logger.info("\n[4/6] Polishing subtitles with LLM...")
        with start_span("llm_polish", model=config.llm_model_name, base_url=config.llm_base_url):
            segments = polish_english_subtitles_with_llm(segments, config)
    return segments


def _write_srt_step(segments: List[Segment], srt_path: Path, config: Config) -> Path:
    """Write segments to SRT file."""
    logger.info("\n[5/6] Writing SRT subtitle file...")
    with start_span("write_srt", output=str(srt_path)):
        # Re-validate constraints before writing
        adjustments = enforce_subtitle_constraints_on_segments(segments, config)
        if adjustments:
            logger.info(f"Applied constraint adjustments to {adjustments} segment(s) before SRT generation")
        srt_path = write_srt_file(segments, str(srt_path), config)
        logger.info(f"✓ SRT file created: {srt_path}")
        return Path(srt_path)


def _mux_subtitles_step(video_path: Path, srt_path: Path, outbox_dir: Path, config: Config, no_mux: bool) -> Optional[Path]:
    """Mux subtitles into video."""
    if no_mux or not config.mux_enabled:
        logger.info("\n[6/6] Skipping video muxing (disabled)")
        return None
    
    logger.info("\n[6/6] Muxing subtitles into video...")
    with start_span("mux_subtitles"):
        suffix = config.mux_output_suffix
        muxed_path = outbox_dir / f"{video_path.stem}.{suffix}{video_path.suffix}"
        muxed_path = mux_subtitle_to_video(
            str(video_path), str(srt_path), str(muxed_path),
            config.get("mux", "subtitle_language", default="eng"),
            config.get("mux", "subtitle_title", default="English")
        )
        logger.info(f"✓ Muxed video created: {muxed_path}")
        return Path(muxed_path)


def process_video(
    video_path: str,
    config: Config,
    no_llm: bool = False,
    no_mux: bool = False,
    audio_track: Optional[int] = None
) -> dict:
    """
    Process a single video file through the complete pipeline.
    
    Args:
        video_path: Path to input video file
        config: Configuration object
        no_llm: Skip LLM polishing step
        no_mux: Skip muxing subtitles into video
        audio_track: Specific audio track index (None = auto-detect)
        
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
    audio_path = Path(config.get_path("temp")) / f"{video_stem}.wav"
    srt_path = Path(config.get_path("outbox")) / f"{video_stem}.en.srt"
    log_path = Path(config.get_path("logs")) / f"{video_stem}.json"
    
    result = {
        "input_video": str(video_path),
        "audio_file": str(audio_path),
        "srt_file": str(srt_path),
        "log_file": str(log_path),
        "muxed_video": None,
        "segment_count": 0,
        "success": False
    }
    
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
        # Step 2: Japanese ASR (Speech to Text)
        # ===================================================================
        logger.info("\n[2/6] Running Japanese ASR (Faster-Whisper)...")
        with start_span("asr_transcription", model=config.asr_model_name, profile=config.profile):
            asr = FasterWhisperASR(config)
            segments = asr.transcribe_audio_to_segments(str(audio_path))
            # TEMP: skip unloading ASR model due to crash after destructor
            # asr.unload_model()
        
        if not segments:
            logger.error("No speech segments detected in audio")
            return result
        
        logger.info(f"Transcribed {len(segments)} Japanese segments (audio track {audio_track})")
        result["segment_count"] = len(segments)
        
        # ===================================================================
        # Step 3: Japanese to English translation
        # ===================================================================
        logger.info("\n[3/6] Translating Japanese to English (MarianMT)...")
        with start_span("machine_translation", model=config.mt_model_name, device=config.mt_device):
            translator = MarianTranslator(config)
            segments = translator.translate_segments_ja_to_en(segments)
            translator.unload_model()
        
        # ===================================================================
        # Step 4: Optional LLM polishing
        # ===================================================================
        if no_llm or not config.llm_enabled:
            logger.info("\n[4/6] Skipping LLM polishing (disabled)")
            with start_span("llm_polish", enabled=False):
                for seg in segments:
                    seg.text_en_final = seg.text_en_raw
        else:
            logger.info("\n[4/6] Polishing subtitles with LLM...")
            with start_span("llm_polish", model=config.llm_model_name, base_url=config.llm_base_url):
                segments = polish_english_subtitles_with_llm(segments, config)
        
        # ===================================================================
        # Step 5: Write SRT file
        # ===================================================================
        logger.info("\n[5/6] Writing SRT subtitle file...")
        with start_span("write_srt", output=str(srt_path)):
            srt_path = write_srt_file(segments, str(srt_path), config)
            logger.info(f"✓ SRT file created: {srt_path}")
        
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
        
        # ===================================================================
        # Save segment log
        # ===================================================================
        if config.get("logging", "save_segment_json", default=True):
            with start_span("save_segment_log", output=str(log_path)):
                save_segment_log(segments, str(log_path))
        
        # ===================================================================
        # Cleanup temp files
        # ===================================================================
        if audio_path.exists():
            audio_path.unlink()
            logger.debug(f"Cleaned up temp file: {audio_path.name}")
        
        result["success"] = True
        
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
        return result


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
    
    # Process video
    try:
        result = process_video(
            video_path=args.video,
            config=config,
            no_llm=args.no_llm,
            no_mux=args.no_mux,
            audio_track=args.audio_track
        )
        
        if result["success"]:
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
