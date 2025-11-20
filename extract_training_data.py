"""
Extract training data from comparison results.

This tool extracts segments that need improvement to build training datasets
for fine-tuning translation or LLM models.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Optional
import subprocess

from compare_subtitles import parse_srt_file, extract_embedded_subtitles

logger = logging.getLogger(__name__)


def extract_audio_segment(
    video_path: str,
    start_time: float,
    end_time: float,
    output_path: str
) -> bool:
    """
    Extract a specific audio segment from video.
    
    Args:
        video_path: Path to video file
        start_time: Start time in seconds
        end_time: End time in seconds
        output_path: Path for output audio file
        
    Returns:
        True if successful
    """
    duration = end_time - start_time
    
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-ss", str(start_time),
        "-t", str(duration),
        "-vn",  # No video
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Failed to extract audio segment: {e}")
        return False


def extract_training_pairs(
    video_path: str,
    comparison_results: Dict,
    segment_log: str,
    output_dir: str,
    min_similarity: float = 0.0,
    max_similarity: float = 0.7,
    extract_audio: bool = False
) -> List[Dict]:
    """
    Extract training pairs from comparison results.
    
    Args:
        video_path: Path to original video
        comparison_results: Results from compare_subtitles
        segment_log: Path to segment JSON log with Japanese text
        output_dir: Directory to save training data
        min_similarity: Minimum similarity threshold (inclusive)
        max_similarity: Maximum similarity threshold (exclusive)
        extract_audio: Whether to extract audio clips
        
    Returns:
        List of training pair dictionaries
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if extract_audio:
        audio_dir = output_dir / "audio_clips"
        audio_dir.mkdir(exist_ok=True)
    
    # Load segment log with Japanese text
    with open(segment_log, 'r', encoding='utf-8') as f:
        segments_data = json.load(f)
    
    # Handle both dict with 'segments' key and list format
    if isinstance(segments_data, dict) and 'segments' in segments_data:
        segments_list = segments_data['segments']
    elif isinstance(segments_data, list):
        segments_list = segments_data
    else:
        raise ValueError(f"Unexpected segments data format: {type(segments_data)}")
    
    # Create lookup by index (1-based index matching generated subtitle indices)
    ja_text_lookup = {i+1: seg for i, seg in enumerate(segments_list)}
    
    training_pairs = []
    
    for match in comparison_results['matches']:
        similarity = match['similarity']
        
        # Filter by similarity range
        if not (min_similarity <= similarity < max_similarity):
            continue
        
        gen_idx = match['generated_index']
        
        if gen_idx not in ja_text_lookup:
            logger.warning(f"Japanese text not found for segment {gen_idx}")
            continue
        
        seg_data = ja_text_lookup[gen_idx]
        
        pair = {
            "index": gen_idx,
            "similarity": similarity,
            "japanese_text": seg_data.get('text_ja', seg_data.get('text', '')),
            "generated_translation": match['generated_text'],
            "reference_translation": match['reference_text'],
            "start_time": seg_data.get('start', seg_data.get('start_time', 0)),
            "end_time": seg_data.get('end', seg_data.get('end_time', 0)),
            "duration": seg_data.get('duration', seg_data.get('end', 0) - seg_data.get('start', 0))
        }
        
        # Extract audio clip if requested
        if extract_audio:
            audio_file = audio_dir / f"segment_{gen_idx:04d}.wav"
            if extract_audio_segment(
                video_path,
                seg_data['start'],
                seg_data['end'],
                str(audio_file)
            ):
                pair['audio_file'] = str(audio_file.relative_to(output_dir))
        
        training_pairs.append(pair)
    
    logger.info(f"Extracted {len(training_pairs)} training pairs")
    logger.info(f"Similarity range: {min_similarity:.0%} - {max_similarity:.0%}")
    
    return training_pairs


def save_training_data(
    training_pairs: List[Dict],
    output_dir: str,
    format: str = "jsonl"
):
    """
    Save training data in specified format.
    
    Args:
        training_pairs: List of training pair dictionaries
        output_dir: Directory to save data
        format: Output format (jsonl, csv, txt)
    """
    output_dir = Path(output_dir)
    
    if format == "jsonl":
        output_file = output_dir / "training_data.jsonl"
        with open(output_file, 'w', encoding='utf-8') as f:
            for pair in training_pairs:
                json.dump(pair, f, ensure_ascii=False)
                f.write('\n')
        logger.info(f"Saved JSONL to {output_file}")
    
    elif format == "csv":
        import csv
        output_file = output_dir / "training_data.csv"
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=training_pairs[0].keys())
            writer.writeheader()
            writer.writerows(training_pairs)
        logger.info(f"Saved CSV to {output_file}")
    
    elif format == "txt":
        # Simple format for LLM fine-tuning
        output_file = output_dir / "training_data.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            for pair in training_pairs:
                f.write(f"### Japanese:\n{pair['japanese_text']}\n\n")
                f.write(f"### Poor Translation:\n{pair['generated_translation']}\n\n")
                f.write(f"### Good Translation:\n{pair['reference_translation']}\n\n")
                f.write("=" * 70 + "\n\n")
        logger.info(f"Saved TXT to {output_file}")
    
    # Also save full JSON for reference
    json_file = output_dir / "training_data.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(training_pairs, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved JSON to {json_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract training data from subtitle comparison results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract segments with 0-70% similarity
  python extract_training_data.py video.mkv comparison.json logs/video.json

  # Extract only very poor translations (0-40%)
  python extract_training_data.py video.mkv comparison.json logs/video.json --max-similarity 0.4

  # Extract with audio clips for ASR training
  python extract_training_data.py video.mkv comparison.json logs/video.json --extract-audio

  # Save in CSV format
  python extract_training_data.py video.mkv comparison.json logs/video.json --format csv
        """
    )
    
    parser.add_argument(
        "video",
        type=str,
        help="Path to video file"
    )
    
    parser.add_argument(
        "comparison_json",
        type=str,
        help="Path to comparison results JSON"
    )
    
    parser.add_argument(
        "segment_log",
        type=str,
        help="Path to segment log JSON (from logs/ directory)"
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="training_data",
        help="Output directory for training data (default: training_data)"
    )
    
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=0.0,
        help="Minimum similarity threshold (default: 0.0)"
    )
    
    parser.add_argument(
        "--max-similarity",
        type=float,
        default=0.7,
        help="Maximum similarity threshold (default: 0.7)"
    )
    
    parser.add_argument(
        "--extract-audio",
        action="store_true",
        help="Extract audio clips for each segment"
    )
    
    parser.add_argument(
        "--format",
        type=str,
        choices=["jsonl", "csv", "txt"],
        default="jsonl",
        help="Output format (default: jsonl)"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load comparison results
    logger.info(f"Loading comparison results from {args.comparison_json}")
    with open(args.comparison_json, 'r', encoding='utf-8') as f:
        comparison_results = json.load(f)
    
    # Extract training pairs
    training_pairs = extract_training_pairs(
        args.video,
        comparison_results,
        args.segment_log,
        args.output_dir,
        args.min_similarity,
        args.max_similarity,
        args.extract_audio
    )
    
    if not training_pairs:
        logger.warning("No training pairs found matching criteria")
        return
    
    # Save training data
    save_training_data(training_pairs, args.output_dir, args.format)
    
    logger.info(f"Training data extraction complete!")
    logger.info(f"Output directory: {args.output_dir}")


if __name__ == "__main__":
    main()
