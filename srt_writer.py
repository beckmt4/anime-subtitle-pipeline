"""
SRT subtitle file writer.

This module handles formatting and writing subtitle files in SRT format.

Key features:
- Proper SRT timestamp formatting (HH:MM:SS,mmm)
- Enforces minimum and maximum subtitle durations
- Splits overly long segments at punctuation marks
- Handles line breaking for readability
- Validates subtitle timing
"""

import logging
import re
from pathlib import Path
from typing import List, Optional

from asr import Segment  # legacy
from models import Segment as GenericSegment, SubtitleCandidate
from config import Config

logger = logging.getLogger(__name__)


def format_timestamp_srt(seconds: float) -> str:
    """
    Format a timestamp in SRT format: HH:MM:SS,mmm
    
    Args:
        seconds: Time in seconds (can have decimal places, must be non-negative)
        
    Returns:
        Formatted timestamp string in SRT format
        
    Raises:
        ValueError: If seconds is negative
        
    Example:
        >>> format_timestamp_srt(90.5)
        '00:01:30,500'
    """
    if seconds < 0:
        raise ValueError(f"Timestamp cannot be negative: {seconds}")
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def split_text_by_punctuation(
    text: str,
    punctuation: List[str],
    target_length: int
) -> List[str]:
    """
    Split text at punctuation marks if it exceeds target length.
    
    Args:
        text: Text to split
        punctuation: List of punctuation marks to split on (e.g., ['.', '!', '?'])
        target_length: Target length in characters before splitting
        
    Returns:
        List of text chunks
    """
    if len(text) <= target_length:
        return [text]
    
    # Build regex pattern for splitting on any of the punctuation marks
    # Pattern matches punctuation followed by space or end of string
    pattern = f"([{''.join(re.escape(p) for p in punctuation)}]\\s+)"
    
    # Split but keep the punctuation
    parts = re.split(pattern, text)
    
    # Reconstruct chunks
    chunks = []
    current_chunk = ""
    
    for part in parts:
        if current_chunk and len(current_chunk + part) > target_length:
            # Current chunk is long enough, save it and start new one
            chunks.append(current_chunk.strip())
            current_chunk = part
        else:
            current_chunk += part
    
    # Add remaining chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks if chunks else [text]


def split_into_lines(text: str, max_chars_per_line: int) -> str:
    """
    Split text into multiple lines for subtitle display.
    
    Tries to split at word boundaries to avoid breaking words.
    
    Args:
        text: Text to split
        max_chars_per_line: Maximum characters per line
        
    Returns:
        Text with newlines inserted
    """
    if len(text) <= max_chars_per_line:
        return text
    
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        # Check if adding this word would exceed the limit
        test_line = f"{current_line} {word}".strip()
        
        if len(test_line) <= max_chars_per_line:
            current_line = test_line
        else:
            # Line would be too long, start a new line
            if current_line:
                lines.append(current_line)
            current_line = word
    
    # Add the last line
    if current_line:
        lines.append(current_line)
    
    return "\n".join(lines)


class SRTWriter:
    """
    SRT subtitle file writer.
    
    Handles conversion of Segment objects to properly formatted SRT files
    with timing and formatting constraints applied.
    """
    
    def __init__(self, config: Config):
        """
        Initialize the SRT writer.
        
        Args:
            config: Configuration object with subtitle settings
        """
        self.config = config
        self.min_duration = config.subtitle_min_duration
        self.max_duration = config.subtitle_max_duration
        self.split_punctuation = config.get("subtitles", "split_on_punctuation", default=[".", "!", "?", ";"])
        self.target_split_length = config.get("subtitles", "target_split_length", default=80)
        self.max_chars_per_line = config.llm_max_chars_per_line
    
    def prepare_segments(self, segments: List[Segment]) -> List[Segment]:
        """
        Prepare segments for writing by applying timing and splitting constraints.
        
        - Enforces minimum duration
        - Splits segments that are too long
        - Validates timing
        
        Args:
            segments: Original list of segments
            
        Returns:
            New list of segments ready for writing
        """
        prepared = []
        
        for seg in segments:
            # Skip empty segments
            if not seg.text_en_final.strip():
                continue
            
            # Enforce minimum duration
            if seg.duration < self.min_duration:
                logger.debug(f"Extending segment duration from {seg.duration:.2f}s to {self.min_duration}s")
                seg.end = seg.start + self.min_duration
            
            # Check if segment needs splitting
            if seg.duration > self.max_duration or len(seg.text_en_final) > self.target_split_length:
                # Try to split by punctuation
                text_chunks = split_text_by_punctuation(
                    seg.text_en_final,
                    self.split_punctuation,
                    self.target_split_length
                )
                
                if len(text_chunks) > 1:
                    # Split the timing proportionally
                    duration_per_chunk = seg.duration / len(text_chunks)
                    # If the proportional slice still exceeds max_duration, cap each
                    # chunk at max_duration. This introduces small gaps between
                    # chunks (the subtitle blanks out before the next chunk starts)
                    # which is standard subtitling practice — better than showing
                    # the same line for longer than max_duration.
                    chunk_duration = min(duration_per_chunk, self.max_duration)
                    capped = duration_per_chunk > self.max_duration

                    for i, chunk in enumerate(text_chunks):
                        chunk_start = seg.start + i * duration_per_chunk
                        new_seg = Segment(
                            start=chunk_start,
                            end=chunk_start + chunk_duration,
                            text_ja=seg.text_ja,  # Keep original for reference
                            text_en_raw=seg.text_en_raw,
                            text_en_final=chunk.strip()
                        )
                        prepared.append(new_seg)

                    if capped:
                        logger.debug(
                            f"Split long segment ({seg.duration:.1f}s) into {len(text_chunks)} parts; "
                            f"each capped at {self.max_duration}s (proportional slice was "
                            f"{duration_per_chunk:.1f}s)"
                        )
                    else:
                        logger.debug(
                            f"Split long segment ({seg.duration:.1f}s) into {len(text_chunks)} parts"
                        )
                    continue
            
            # No splitting needed (or split_text_by_punctuation returned a single
            # chunk because the text was shorter than target_split_length, or
            # contained no splittable punctuation). If the duration still
            # exceeds max_duration, cap the end time rather than display the
            # same subtitle for too long. Standard subtitling practice.
            if seg.duration > self.max_duration:
                old_duration = seg.duration
                seg.end = seg.start + self.max_duration
                logger.debug(
                    f"Capped segment duration from {old_duration:.1f}s to "
                    f"{self.max_duration}s (text not splittable at punctuation)"
                )

            prepared.append(seg)

        return prepared
    
    def write_srt(self, segments: List[Segment], output_path: str) -> Path:
        """
        Write segments to an SRT file.
        
        Args:
            segments: List of Segment objects with text_en_final populated
            output_path: Path for output SRT file
            
        Returns:
            Path object pointing to the written file
            
        Raises:
            ValueError: If segments list is empty
        """
        if not segments:
            raise ValueError("Cannot write SRT file: no segments provided")
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Prepare segments (apply constraints)
        segments = self.prepare_segments(segments)
        
        if not segments:
            raise ValueError("Cannot write SRT file: all segments were filtered out")
        
        logger.info(f"Writing {len(segments)} subtitles to {output_path.name}")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(segments, start=1):
                # SRT format:
                # 1
                # 00:00:01,000 --> 00:00:04,000
                # Subtitle text
                # (blank line)
                
                # Format text with line breaks
                text = split_into_lines(seg.text_en_final, self.max_chars_per_line)
                
                # Write subtitle entry
                f.write(f"{i}\n")
                f.write(f"{format_timestamp_srt(seg.start)} --> {format_timestamp_srt(seg.end)}\n")
                f.write(f"{text}\n")
                f.write("\n")
        
        file_size_kb = output_path.stat().st_size / 1024
        logger.info(f"SRT file written: {file_size_kb:.1f} KB")
        
        return output_path
    
    def validate_segments(self, segments: List[Segment]) -> List[str]:
        """
        Validate segments for common issues.
        
        Returns a list of warning messages (empty if no issues).
        
        Args:
            segments: List of segments to validate
            
        Returns:
            List of warning messages
        """
        warnings = []
        
        for i, seg in enumerate(segments):
            # Check timing
            if seg.start >= seg.end:
                warnings.append(f"Segment {i+1}: start time >= end time ({seg.start:.2f} >= {seg.end:.2f})")
            
            if seg.duration < 0.1:
                warnings.append(f"Segment {i+1}: duration too short ({seg.duration:.2f}s)")
            
            # Check text
            if not seg.text_en_final.strip():
                warnings.append(f"Segment {i+1}: empty text")
            
            # Check overlap with next segment
            if i < len(segments) - 1:
                next_seg = segments[i + 1]
                if seg.end > next_seg.start:
                    warnings.append(
                        f"Segment {i+1}: overlaps with next segment "
                        f"({seg.end:.2f} > {next_seg.start:.2f})"
                    )
        
        return warnings


def write_srt_file(segments: List[Segment], output_path: str, config: Config) -> Path:
    """
    Convenience function to write an SRT file.
    
    Args:
        segments: List of Segment objects with English text
        output_path: Output file path
        config: Configuration object
        
    Returns:
        Path to written SRT file
    """
    writer = SRTWriter(config)
    
    # Validate before writing
    warnings = writer.validate_segments(segments)
    if warnings:
        logger.warning(f"Found {len(warnings)} validation warnings:")
        for warning in warnings[:5]:  # Show first 5
            logger.warning(f"  {warning}")
        if len(warnings) > 5:
            logger.warning(f"  ... and {len(warnings) - 5} more")
    
    return writer.write_srt(segments, output_path)


# ---------------------------------------------------------------------------
# New unified candidate SRT helpers
# ---------------------------------------------------------------------------
def write_candidate_srt(candidate: SubtitleCandidate, output_path: str, config: Config) -> Path:
    """Write a SubtitleCandidate to SRT using its segment texts."""
    writer = SRTWriter(config)
    # Convert candidate segments to legacy style temporary objects for existing pipeline logic
    temp_segments: List[Segment] = []
    for s in candidate.segments:
        temp_segments.append(
            Segment(start=s.start, end=s.end, text_ja="", text_en_raw=s.text, text_en_final=s.text)
        )
    warnings = writer.validate_segments(temp_segments)
    if warnings:
        logger.warning(f"Found {len(warnings)} validation warnings for candidate {candidate.id}")
    return writer.write_srt(temp_segments, output_path)

__all__ = [
    "format_timestamp_srt",
    "write_srt_file",
    "write_candidate_srt",
    "read_srt_file",
]


# Utility: Read SRT file back into segments (for testing/validation)
def read_srt_file(srt_path: str) -> List[Segment]:
    """
    Read an SRT file and parse it into Segment objects.
    
    This is useful for testing and validation. The Japanese text fields
    will be empty since SRT only contains English.
    
    Args:
        srt_path: Path to SRT file
        
    Returns:
        List of Segment objects
    """
    srt_path = Path(srt_path)
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT file not found: {srt_path}")
    
    segments = []
    
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # SRT blocks are separated by blank lines
    blocks = content.strip().split('\n\n')
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        
        # Parse timestamp line (line 1, 0-indexed)
        timestamp_line = lines[1]
        match = re.match(
            r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})',
            timestamp_line
        )
        
        if match:
            h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, match.groups())
            start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
            end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
            
            # Text is all remaining lines
            text = '\n'.join(lines[2:])
            
            seg = Segment(
                start=start,
                end=end,
                text_ja="",  # Not available from SRT
                text_en_raw="",
                text_en_final=text
            )
            segments.append(seg)
    
    logger.info(f"Read {len(segments)} segments from {srt_path.name}")
    
    return segments
