"""
Example usage script demonstrating the anime subtitle pipeline API.

This script shows how to use the pipeline components programmatically
instead of using the CLI.
"""

from pathlib import Path
from config import Config, set_config
from audio_utils import extract_audio_with_ffmpeg
from asr import FasterWhisperASR
from mt import MarianTranslator
from llm_polish import LLMPolisher
from srt_writer import write_srt_file
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_full_pipeline():
    """
    Example: Process a video through the complete pipeline.
    """
    # Load configuration
    config = Config("config.yaml")
    set_config(config)
    
    # Input video
    video_path = "inbox/test_video.mkv"
    
    # Extract audio
    audio_path = "temp/test_audio.wav"
    extract_audio_with_ffmpeg(video_path, audio_path)
    
    # Transcribe (ASR)
    asr = FasterWhisperASR(config)
    segments, _ = asr.transcribe_audio_to_segments(audio_path)
    asr.unload_model()
    
    logger.info(f"Transcribed {len(segments)} segments")
    
    # Translate
    translator = MarianTranslator(config)
    segments = translator.translate_segments_ja_to_en(segments)
    translator.unload_model()
    
    # Polish (optional)
    if config.llm_enabled:
        polisher = LLMPolisher(config)
        segments = polisher.polish_segments(segments)
    else:
        for seg in segments:
            seg.text_en_final = seg.text_en_raw
    
    # Write SRT
    srt_path = "outbox/test_video.en.srt"
    write_srt_file(segments, srt_path, config)
    
    logger.info(f"✓ Complete! SRT saved to {srt_path}")


def example_batch_processing():
    """
    Example: Process multiple videos efficiently by keeping models loaded.
    """
    config = Config("config.yaml")
    set_config(config)
    
    # List of videos to process
    video_files = list(Path("inbox").glob("*.mkv"))
    
    # Initialize models once
    asr = FasterWhisperASR(config)
    asr.load_model()
    
    translator = MarianTranslator(config)
    translator.load_model()
    
    polisher = LLMPolisher(config) if config.llm_enabled else None
    
    # Process each video
    for video_path in video_files:
        logger.info(f"Processing {video_path.name}...")
        
        # Extract audio
        audio_path = f"temp/{video_path.stem}.wav"
        extract_audio_with_ffmpeg(str(video_path), audio_path)
        
        # Transcribe
        segments, _ = asr.transcribe_audio_to_segments(audio_path)
        
        # Translate
        segments = translator.translate_segments_ja_to_en(segments)
        
        # Polish
        if polisher:
            segments = polisher.polish_segments(segments)
        else:
            for seg in segments:
                seg.text_en_final = seg.text_en_raw
        
        # Write SRT
        srt_path = f"outbox/{video_path.stem}.en.srt"
        write_srt_file(segments, srt_path, config)
        
        logger.info(f"✓ {video_path.name} complete!")
    
    # Clean up
    asr.unload_model()
    translator.unload_model()
    
    logger.info(f"✓ Batch processing complete! Processed {len(video_files)} videos")


def example_custom_processing():
    """
    Example: Custom processing with manual control over each step.
    """
    config = Config("config.yaml")
    set_config(config)
    
    video_path = "inbox/test_video.mkv"
    audio_path = "temp/test_audio.wav"
    
    # Extract audio
    extract_audio_with_ffmpeg(video_path, audio_path, audio_track_index=1)
    
    # Transcribe with custom language
    asr = FasterWhisperASR(config)
    segments, _ = asr.transcribe_audio_to_segments(audio_path, language="ja")
    
    # Filter out very short segments
    segments = [seg for seg in segments if seg.duration >= 0.5]
    
    # Translate
    translator = MarianTranslator(config)
    segments = translator.translate_segments_ja_to_en(segments)
    
    # Custom polishing: use literal style
    if config.llm_enabled:
        polisher = LLMPolisher(config)
        segments = polisher.polish_segments(segments, style="literal")
    else:
        for seg in segments:
            seg.text_en_final = seg.text_en_raw
    
    # Manually adjust some segments (example)
    for seg in segments:
        # Replace specific terms
        seg.text_en_final = seg.text_en_final.replace("Mr.", "San")
        seg.text_en_final = seg.text_en_final.replace("Miss", "Chan")
    
    # Write SRT
    srt_path = "outbox/test_video.custom.srt"
    write_srt_file(segments, srt_path, config)
    
    logger.info(f"✓ Custom processing complete!")


def example_inspect_segments():
    """
    Example: Load and inspect segment data from a previous run.
    """
    import json
    
    # Load segment log from previous processing
    log_path = "logs/test_video.json"
    
    with open(log_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Analyze segments
    total_segments = len(data)
    total_duration = sum(seg['duration'] for seg in data)
    avg_duration = total_duration / total_segments if total_segments > 0 else 0
    
    logger.info(f"Segment Analysis for {log_path}:")
    logger.info(f"  Total segments: {total_segments}")
    logger.info(f"  Total duration: {total_duration:.2f}s")
    logger.info(f"  Average duration: {avg_duration:.2f}s")
    
    # Show some examples
    logger.info("\nExample segments:")
    for i, seg in enumerate(data[:3], 1):
        logger.info(f"\nSegment {i}:")
        logger.info(f"  Time: {seg['start']:.2f}s - {seg['end']:.2f}s")
        logger.info(f"  Japanese: {seg['text_ja']}")
        logger.info(f"  English (raw): {seg['text_en_raw']}")
        logger.info(f"  English (final): {seg['text_en_final']}")


if __name__ == "__main__":
    # Run examples (comment out the ones you don't need)
    
    # Example 1: Full pipeline for a single video
    # example_full_pipeline()
    
    # Example 2: Batch processing multiple videos
    # example_batch_processing()
    
    # Example 3: Custom processing with manual control
    # example_custom_processing()
    
    # Example 4: Inspect segment data
    # example_inspect_segments()
    
    logger.info("Example script ready. Uncomment the example you want to run.")
