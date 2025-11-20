"""
Compare generated subtitles with existing embedded subtitles.

This tool extracts embedded subtitles from a video file and compares them
with the generated subtitles to provide accuracy metrics.
"""

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import difflib
import re

logger = logging.getLogger(__name__)


class SubtitleSegment:
    """Represents a single subtitle segment."""
    
    def __init__(self, index: int, start: float, end: float, text: str):
        self.index = index
        self.start = start
        self.end = end
        self.text = text.strip()
    
    def __repr__(self):
        return f"Segment({self.index}, {self.start:.2f}-{self.end:.2f}, '{self.text[:30]}...')"


def extract_embedded_subtitles(video_path: str, subtitle_track: int = 0, language: str = "eng") -> Optional[str]:
    """
    Extract embedded subtitles from video using ffmpeg.
    
    Args:
        video_path: Path to video file
        subtitle_track: Index of subtitle track to extract
        language: Language code to filter (e.g., 'eng', 'jpn')
        
    Returns:
        Path to extracted SRT file, or None if extraction failed
    """
    video_path = Path(video_path)
    output_path = video_path.parent / f"{video_path.stem}_embedded.srt"
    
    logger.info(f"Extracting embedded subtitles from {video_path.name}")
    logger.info(f"  Track: {subtitle_track}")
    logger.info(f"  Language filter: {language}")
    
    # First, list available subtitle tracks
    list_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "s",
        "-show_entries", "stream=index,codec_name:stream_tags=language,title",
        "-of", "json",
        str(video_path)
    ]
    
    try:
        result = subprocess.run(list_cmd, capture_output=True, text=True, check=True)
        streams = json.loads(result.stdout)
        
        if "streams" not in streams or not streams["streams"]:
            logger.error("No subtitle tracks found in video")
            return None
        
        logger.info(f"Found {len(streams['streams'])} subtitle track(s):")
        for i, stream in enumerate(streams["streams"]):
            lang = stream.get("tags", {}).get("language", "unknown")
            title = stream.get("tags", {}).get("title", "")
            codec = stream.get("codec_name", "unknown")
            logger.info(f"  Track {i}: {lang} ({codec}) - {title}")
        
        # Extract the subtitle
        extract_cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-map", f"0:s:{subtitle_track}",
            "-c:s", "srt",
            str(output_path)
        ]
        
        result = subprocess.run(extract_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"ffmpeg failed: {result.stderr}")
            return None
        
        if output_path.exists():
            logger.info(f"Extracted subtitles to: {output_path}")
            return str(output_path)
        else:
            logger.error("Extraction appeared successful but output file not found")
            return None
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to extract subtitles: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse ffprobe output: {e}")
        return None


def parse_srt_file(srt_path: str) -> List[SubtitleSegment]:
    """
    Parse an SRT file into subtitle segments.
    
    Args:
        srt_path: Path to SRT file
        
    Returns:
        List of SubtitleSegment objects
    """
    segments = []
    
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by double newline (segment separator)
    raw_segments = re.split(r'\n\n+', content.strip())
    
    for raw_seg in raw_segments:
        lines = raw_seg.strip().split('\n')
        if len(lines) < 3:
            continue
        
        try:
            # Parse index
            index = int(lines[0].strip())
            
            # Parse timestamps
            timestamp_line = lines[1].strip()
            start_str, end_str = timestamp_line.split(' --> ')
            start = parse_srt_timestamp(start_str)
            end = parse_srt_timestamp(end_str)
            
            # Parse text (can be multiple lines)
            text = '\n'.join(lines[2:])
            
            segments.append(SubtitleSegment(index, start, end, text))
            
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse segment: {e}")
            continue
    
    return segments


def parse_srt_timestamp(timestamp: str) -> float:
    """
    Convert SRT timestamp to seconds.
    
    Args:
        timestamp: Timestamp in format HH:MM:SS,mmm
        
    Returns:
        Time in seconds
    """
    # Remove any extra whitespace
    timestamp = timestamp.strip()
    
    # Split by comma to separate milliseconds
    time_part, ms_part = timestamp.split(',')
    h, m, s = time_part.split(':')
    
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms_part) / 1000


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison.
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text
    """
    # Convert to lowercase
    text = text.lower()
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    
    # Remove common punctuation variations
    text = text.replace('\n', ' ')
    text = re.sub(r'[^\w\s]', '', text)
    
    return text.strip()


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity ratio between two texts.
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Similarity ratio (0.0 to 1.0)
    """
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    
    return difflib.SequenceMatcher(None, norm1, norm2).ratio()


def find_matching_segment(
    segment: SubtitleSegment,
    candidates: List[SubtitleSegment],
    time_tolerance: float = 2.0
) -> Optional[SubtitleSegment]:
    """
    Find the best matching segment based on timing.
    
    Args:
        segment: Segment to match
        candidates: List of candidate segments
        time_tolerance: Maximum time difference in seconds
        
    Returns:
        Best matching segment or None
    """
    best_match = None
    best_overlap = 0.0
    
    for candidate in candidates:
        # Calculate temporal overlap
        overlap_start = max(segment.start, candidate.start)
        overlap_end = min(segment.end, candidate.end)
        
        if overlap_end > overlap_start:
            overlap = overlap_end - overlap_start
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = candidate
    
    # If no overlap found, try finding by start time proximity
    if best_match is None:
        min_distance = float('inf')
        for candidate in candidates:
            distance = abs(segment.start - candidate.start)
            if distance < min_distance and distance <= time_tolerance:
                min_distance = distance
                best_match = candidate
    
    return best_match


def compare_subtitles(
    generated_srt: str,
    reference_srt: str,
    time_tolerance: float = 2.0
) -> Dict:
    """
    Compare generated subtitles with reference subtitles.
    
    Args:
        generated_srt: Path to generated SRT file
        reference_srt: Path to reference SRT file
        time_tolerance: Maximum time difference for matching segments
        
    Returns:
        Dictionary with comparison results
    """
    logger.info("Parsing generated subtitles...")
    generated = parse_srt_file(generated_srt)
    
    logger.info("Parsing reference subtitles...")
    reference = parse_srt_file(reference_srt)
    
    logger.info(f"Generated segments: {len(generated)}")
    logger.info(f"Reference segments: {len(reference)}")
    
    # Match segments and calculate similarities
    matches = []
    similarities = []
    
    for gen_seg in generated:
        ref_seg = find_matching_segment(gen_seg, reference, time_tolerance)
        
        if ref_seg:
            similarity = calculate_similarity(gen_seg.text, ref_seg.text)
            similarities.append(similarity)
            
            matches.append({
                "generated_index": gen_seg.index,
                "reference_index": ref_seg.index,
                "generated_text": gen_seg.text,
                "reference_text": ref_seg.text,
                "similarity": similarity,
                "time_diff": abs(gen_seg.start - ref_seg.start)
            })
    
    # Calculate statistics
    avg_similarity = sum(similarities) / len(similarities) if similarities else 0.0
    matched_count = len(matches)
    match_rate = matched_count / len(generated) if generated else 0.0
    
    results = {
        "generated_count": len(generated),
        "reference_count": len(reference),
        "matched_count": matched_count,
        "match_rate": match_rate,
        "average_similarity": avg_similarity,
        "matches": matches
    }
    
    return results


def print_comparison_report(results: Dict, show_details: bool = False):
    """
    Print a formatted comparison report.
    
    Args:
        results: Comparison results dictionary
        show_details: Whether to show detailed segment comparisons
    """
    print("\n" + "=" * 70)
    print("SUBTITLE COMPARISON REPORT")
    print("=" * 70)
    
    print(f"\nSegment Counts:")
    print(f"  Generated:  {results['generated_count']}")
    print(f"  Reference:  {results['reference_count']}")
    print(f"  Matched:    {results['matched_count']} ({results['match_rate']*100:.1f}%)")
    
    print(f"\nSimilarity:")
    print(f"  Average:    {results['average_similarity']*100:.1f}%")
    
    # Categorize by similarity
    matches = results['matches']
    excellent = sum(1 for m in matches if m['similarity'] >= 0.9)
    good = sum(1 for m in matches if 0.7 <= m['similarity'] < 0.9)
    fair = sum(1 for m in matches if 0.5 <= m['similarity'] < 0.7)
    poor = sum(1 for m in matches if m['similarity'] < 0.5)
    
    print(f"\nQuality Distribution:")
    print(f"  Excellent (≥90%): {excellent} ({excellent/len(matches)*100:.1f}%)" if matches else "  N/A")
    print(f"  Good (70-89%):    {good} ({good/len(matches)*100:.1f}%)" if matches else "  N/A")
    print(f"  Fair (50-69%):    {fair} ({fair/len(matches)*100:.1f}%)" if matches else "  N/A")
    print(f"  Poor (<50%):      {poor} ({poor/len(matches)*100:.1f}%)" if matches else "  N/A")
    
    if show_details and matches:
        print(f"\n" + "=" * 70)
        print("DETAILED SEGMENT COMPARISON (First 10)")
        print("=" * 70)
        
        for i, match in enumerate(matches[:10]):
            print(f"\nSegment {i+1}:")
            print(f"  Similarity: {match['similarity']*100:.1f}%")
            print(f"  Time diff:  {match['time_diff']:.2f}s")
            print(f"  Generated:  {match['generated_text'][:100]}")
            print(f"  Reference:  {match['reference_text'][:100]}")
    
    print("\n" + "=" * 70)


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Compare generated subtitles with embedded reference subtitles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare with first English subtitle track
  python compare_subtitles.py video.mkv generated.srt
  
  # Specify subtitle track index
  python compare_subtitles.py video.mkv generated.srt --subtitle-track 1
  
  # Show detailed comparison
  python compare_subtitles.py video.mkv generated.srt --details
  
  # Save results to JSON
  python compare_subtitles.py video.mkv generated.srt --output results.json
        """
    )
    
    parser.add_argument(
        "video",
        type=str,
        help="Path to video file with embedded subtitles"
    )
    
    parser.add_argument(
        "generated_srt",
        type=str,
        help="Path to generated SRT file"
    )
    
    parser.add_argument(
        "--subtitle-track",
        type=int,
        default=0,
        help="Subtitle track index to extract (default: 0)"
    )
    
    parser.add_argument(
        "--language",
        type=str,
        default="eng",
        help="Language code filter (default: eng)"
    )
    
    parser.add_argument(
        "--time-tolerance",
        type=float,
        default=2.0,
        help="Time tolerance for matching segments in seconds (default: 2.0)"
    )
    
    parser.add_argument(
        "--details",
        action="store_true",
        help="Show detailed segment-by-segment comparison"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="Save results to JSON file"
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
    
    # Extract embedded subtitles
    reference_srt = extract_embedded_subtitles(
        args.video,
        args.subtitle_track,
        args.language
    )
    
    if not reference_srt:
        logger.error("Failed to extract embedded subtitles")
        sys.exit(1)
    
    # Compare subtitles
    results = compare_subtitles(
        args.generated_srt,
        reference_srt,
        args.time_tolerance
    )
    
    # Print report
    print_comparison_report(results, args.details)
    
    # Save to JSON if requested
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"Results saved to {args.output}")
    
    # Clean up extracted reference file
    try:
        Path(reference_srt).unlink()
        logger.debug(f"Cleaned up temporary file: {reference_srt}")
    except (FileNotFoundError, PermissionError, OSError) as e:
        logger.warning(f"Failed to clean up temp file: {e}")


if __name__ == "__main__":
    main()
