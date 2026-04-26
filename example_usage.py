"""Example usage script demonstrating the anime subtitle pipeline API.

This script shows how to use the pipeline components programmatically
instead of using the CLI.  All examples use the current candidate-based API.
"""

from pathlib import Path
from config import Config, set_config
from audio_utils import extract_audio_with_ffmpeg
from asr import FasterWhisperASR, transcribe_audio_to_candidate
from mt import translate_candidate_jp_to_en
from llm_polish import polish_candidate_with_llm, enforce_constraints_on_candidate
from srt_writer import write_candidate_srt
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_full_pipeline():
    """Process a video through the complete pipeline."""
    config = Config("config.yaml")
    set_config(config)

    video_path = "inbox/test_video.mkv"
    audio_path = "temp/test_audio.wav"

    extract_audio_with_ffmpeg(video_path, audio_path)

    ja_candidate = transcribe_audio_to_candidate(audio_path, config, language="ja")
    logger.info(f"Transcribed {len(ja_candidate.segments)} segments")

    mt_candidate = translate_candidate_jp_to_en(ja_candidate, config)

    if config.llm_enabled:
        polished = polish_candidate_with_llm(mt_candidate, config, ja_candidate=ja_candidate)
        final_candidate = enforce_constraints_on_candidate(polished, config)
    else:
        final_candidate = mt_candidate

    srt_path = write_candidate_srt(final_candidate, "outbox/test_video.en.srt", config)
    logger.info(f"Complete! SRT saved to {srt_path}")


def example_batch_processing():
    """Process multiple videos efficiently by keeping models loaded."""
    config = Config("config.yaml")
    set_config(config)

    video_files = list(Path("inbox").glob("*.mkv"))

    asr = FasterWhisperASR(config)
    asr.load_model()

    for video_path in video_files:
        logger.info(f"Processing {video_path.name}...")

        audio_path = f"temp/{video_path.stem}.wav"
        extract_audio_with_ffmpeg(str(video_path), audio_path)

        _, ja_candidate = asr.transcribe_audio_to_segments(audio_path, language="ja")
        mt_candidate = translate_candidate_jp_to_en(ja_candidate, config)

        if config.llm_enabled:
            polished = polish_candidate_with_llm(mt_candidate, config, ja_candidate=ja_candidate)
            final_candidate = enforce_constraints_on_candidate(polished, config)
        else:
            final_candidate = mt_candidate

        srt_path = write_candidate_srt(final_candidate, f"outbox/{video_path.stem}.en.srt", config)
        logger.info(f"{video_path.name} complete! → {srt_path}")

    asr.unload_model()
    logger.info(f"Batch processing complete! Processed {len(video_files)} videos")


def example_custom_processing():
    """Custom processing with manual control over each step."""
    config = Config("config.yaml")
    set_config(config)

    audio_path = "temp/test_audio.wav"
    extract_audio_with_ffmpeg("inbox/test_video.mkv", audio_path, audio_track_index=1)

    ja_candidate = transcribe_audio_to_candidate(audio_path, config, language="ja")

    # Filter out very short segments before translation
    from models import SubtitleCandidate, Segment as GenericSegment
    short_filtered = SubtitleCandidate(
        id=ja_candidate.id,
        language=ja_candidate.language,
        source=ja_candidate.source,
        origin_stream=ja_candidate.origin_stream,
        segments=[s for s in ja_candidate.segments if (s.end - s.start) >= 0.5],
        meta=ja_candidate.meta,
    )

    mt_candidate = translate_candidate_jp_to_en(short_filtered, config)

    if config.llm_enabled:
        polished = polish_candidate_with_llm(mt_candidate, config, style="literal")
        final_candidate = enforce_constraints_on_candidate(polished, config)
    else:
        final_candidate = mt_candidate

    srt_path = write_candidate_srt(final_candidate, "outbox/test_video.custom.srt", config)
    logger.info(f"Custom processing complete! → {srt_path}")


if __name__ == "__main__":
    # Uncomment the example you want to run.

    # Example 1: Full pipeline for a single video
    # example_full_pipeline()

    # Example 2: Batch processing multiple videos
    # example_batch_processing()

    # Example 3: Custom processing with manual control
    # example_custom_processing()

    logger.info("Example script ready. Uncomment the example you want to run.")
