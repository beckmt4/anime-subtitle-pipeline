"""
Build a comprehensive training dataset from multiple videos.

This tool processes a collection of videos with reference subtitles
and creates a large-scale training dataset for model improvement.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

logger = logging.getLogger(__name__)


def find_videos_with_subtitles(directory: str, extensions: List[str] = None) -> List[Path]:
    """
    Find all video files in directory.
    
    Args:
        directory: Directory to search
        extensions: List of video extensions (default: mkv, mp4, avi)
        
    Returns:
        List of video file paths
    """
    if extensions is None:
        extensions = ['.mkv', '.mp4', '.avi']
    
    directory = Path(directory)
    videos = []
    
    for ext in extensions:
        videos.extend(directory.glob(f"**/*{ext}"))
    
    logger.info(f"Found {len(videos)} video files in {directory}")
    return videos


def check_video_has_subtitles(video_path: str) -> bool:
    """
    Check if video has embedded subtitles.
    
    Args:
        video_path: Path to video file
        
    Returns:
        True if video has subtitle tracks
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index",
        "-of", "json",
        str(video_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False
        
        data = json.loads(result.stdout)
        return bool(data.get("streams", []))
        
    except Exception:
        return False


def process_single_video(
    video_path: Path,
    output_dir: Path,
    min_similarity: float,
    max_similarity: float,
    extract_audio: bool
) -> Dict:
    """
    Process a single video to extract training data.
    
    Args:
        video_path: Path to video file
        output_dir: Output directory for this video's data
        min_similarity: Minimum similarity threshold
        max_similarity: Maximum similarity threshold
        extract_audio: Whether to extract audio clips
        
    Returns:
        Dictionary with processing results
    """
    video_name = video_path.stem
    video_output = output_dir / video_name
    video_output.mkdir(parents=True, exist_ok=True)
    
    result = {
        "video": str(video_path),
        "success": False,
        "pairs_extracted": 0
    }
    
    try:
        # Step 1: Generate subtitles
        logger.info(f"Generating subtitles for {video_name}")
        gen_cmd = ["python", "main.py", str(video_path), "--no-llm"]
        gen_result = subprocess.run(gen_cmd, capture_output=True, text=True)
        
        if gen_result.returncode != 0:
            result["error"] = "Subtitle generation failed"
            return result
        
        # Step 2: Compare with reference
        srt_file = Path("outbox") / f"{video_name}.en.srt"
        log_file = Path("logs") / f"{video_name}.json"
        comparison_file = video_output / "comparison.json"
        
        if not srt_file.exists() or not log_file.exists():
            result["error"] = "Output files not found"
            return result
        
        logger.info(f"Comparing with reference for {video_name}")
        cmp_cmd = [
            "python", "compare_subtitles.py",
            str(video_path),
            str(srt_file),
            "--output", str(comparison_file)
        ]
        cmp_result = subprocess.run(cmp_cmd, capture_output=True, text=True)
        
        if cmp_result.returncode != 0 or not comparison_file.exists():
            result["error"] = "Comparison failed"
            return result
        
        # Step 3: Extract training pairs
        logger.info(f"Extracting training pairs for {video_name}")
        extract_cmd = [
            "python", "extract_training_data.py",
            str(video_path),
            str(comparison_file),
            str(log_file),
            "--output-dir", str(video_output),
            "--min-similarity", str(min_similarity),
            "--max-similarity", str(max_similarity),
            "--format", "jsonl"
        ]
        
        if extract_audio:
            extract_cmd.append("--extract-audio")
        
        extract_result = subprocess.run(extract_cmd, capture_output=True, text=True)
        
        if extract_result.returncode != 0:
            result["error"] = "Training data extraction failed"
            return result
        
        # Count extracted pairs
        training_file = video_output / "training_data.jsonl"
        if training_file.exists():
            with open(training_file, 'r', encoding='utf-8') as f:
                pairs_count = sum(1 for _ in f)
            result["pairs_extracted"] = pairs_count
        
        result["success"] = True
        result["output_dir"] = str(video_output)
        
        logger.info(f"Completed {video_name}: {result['pairs_extracted']} pairs")
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Error processing {video_name}: {e}")
    
    return result


def merge_datasets(output_dirs: List[Path], merged_output: Path):
    """
    Merge training data from multiple videos into single files.
    
    Args:
        output_dirs: List of output directories for individual videos
        merged_output: Directory for merged dataset
    """
    merged_output.mkdir(parents=True, exist_ok=True)
    
    all_pairs = []
    
    # Collect all pairs
    for video_dir in output_dirs:
        jsonl_file = video_dir / "training_data.jsonl"
        if jsonl_file.exists():
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line in f:
                    pair = json.loads(line)
                    pair['source_video'] = video_dir.name
                    all_pairs.append(pair)
    
    logger.info(f"Collected {len(all_pairs)} total training pairs")
    
    # Save merged JSONL
    merged_jsonl = merged_output / "merged_training_data.jsonl"
    with open(merged_jsonl, 'w', encoding='utf-8') as f:
        for pair in all_pairs:
            json.dump(pair, f, ensure_ascii=False)
            f.write('\n')
    
    # Save merged JSON
    merged_json = merged_output / "merged_training_data.json"
    with open(merged_json, 'w', encoding='utf-8') as f:
        json.dump(all_pairs, f, ensure_ascii=False, indent=2)
    
    # Create summary
    summary = {
        "total_pairs": len(all_pairs),
        "total_videos": len(output_dirs),
        "avg_pairs_per_video": len(all_pairs) / len(output_dirs) if output_dirs else 0,
        "output_files": {
            "jsonl": str(merged_jsonl),
            "json": str(merged_json)
        }
    }
    
    summary_file = merged_output / "dataset_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    
    logger.info(f"Merged dataset saved to {merged_output}")
    logger.info(f"Total pairs: {len(all_pairs)}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build training dataset from multiple videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build dataset from all videos in directory
  python build_dataset.py ~/anime_collection --output dataset

  # Extract only poor translations (0-50% similarity)
  python build_dataset.py ~/anime_collection --output dataset --max-similarity 0.5

  # Extract with audio clips and use 4 parallel workers
  python build_dataset.py ~/anime_collection --output dataset --extract-audio --workers 4

  # Process specific video files
  python build_dataset.py video1.mkv video2.mkv video3.mkv --output dataset
        """
    )
    
    parser.add_argument(
        "paths",
        type=str,
        nargs='+',
        help="Directory containing videos, or individual video files"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output directory for training dataset"
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
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers (default: 1)"
    )
    
    parser.add_argument(
        "--skip-subtitle-check",
        action="store_true",
        help="Skip checking for embedded subtitles"
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
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect video files
    videos = []
    for path_str in args.paths:
        path = Path(path_str)
        if path.is_dir():
            videos.extend(find_videos_with_subtitles(str(path)))
        elif path.is_file():
            videos.append(path)
    
    if not videos:
        logger.error("No video files found")
        sys.exit(1)
    
    logger.info(f"Found {len(videos)} video files to process")
    
    # Filter videos with subtitles
    if not args.skip_subtitle_check:
        logger.info("Checking for embedded subtitles...")
        videos_with_subs = [v for v in tqdm(videos) if check_video_has_subtitles(str(v))]
        logger.info(f"{len(videos_with_subs)} videos have embedded subtitles")
        videos = videos_with_subs
    
    if not videos:
        logger.error("No videos with subtitles found")
        sys.exit(1)
    
    # Process videos
    results = []
    video_outputs = []
    
    if args.workers > 1:
        logger.info(f"Processing videos with {args.workers} workers...")
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    process_single_video,
                    video,
                    output_dir / "individual",
                    args.min_similarity,
                    args.max_similarity,
                    args.extract_audio
                ): video for video in videos
            }
            
            for future in tqdm(as_completed(futures), total=len(videos)):
                result = future.result()
                results.append(result)
                if result['success']:
                    video_outputs.append(Path(result['output_dir']))
    else:
        logger.info("Processing videos sequentially...")
        for video in tqdm(videos):
            result = process_single_video(
                video,
                output_dir / "individual",
                args.min_similarity,
                args.max_similarity,
                args.extract_audio
            )
            results.append(result)
            if result['success']:
                video_outputs.append(Path(result['output_dir']))
    
    # Merge datasets
    if video_outputs:
        logger.info("Merging datasets...")
        merge_datasets(video_outputs, output_dir / "merged")
    
    # Save processing results
    results_file = output_dir / "processing_results.json"
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    successful = sum(1 for r in results if r['success'])
    total_pairs = sum(r.get('pairs_extracted', 0) for r in results)
    
    print("\n" + "=" * 70)
    print("DATASET BUILD COMPLETE")
    print("=" * 70)
    print(f"\nProcessed: {len(results)} videos")
    print(f"Successful: {successful}")
    print(f"Total training pairs: {total_pairs}")
    print(f"\nOutput directory: {output_dir}")
    print(f"Merged dataset: {output_dir / 'merged'}")


if __name__ == "__main__":
    main()
