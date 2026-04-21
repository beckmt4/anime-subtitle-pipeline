"""
Audio extraction utilities using ffmpeg.

This module handles extracting audio tracks from video files using ffmpeg.
Provides functions to:
- List available audio tracks in a video file
- Extract a specific audio track to WAV format optimized for Whisper
- Validate ffmpeg installation
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AudioTrackInfo:
    """Information about an audio track in a video file."""
    
    def __init__(self, index: int, codec: str, channels: int, 
                 sample_rate: int, language: Optional[str] = None):
        self.index = index
        self.codec = codec
        self.channels = channels
        self.sample_rate = sample_rate
        self.language = language
    
    def __repr__(self) -> str:
        lang = f", lang={self.language}" if self.language else ""
        return (f"AudioTrack(index={self.index}, codec={self.codec}, "
                f"channels={self.channels}, rate={self.sample_rate}{lang})")


def check_ffmpeg_available() -> bool:
    """
    Check if ffmpeg is available on the system.
    
    Attempts to run 'ffmpeg -version' to verify the executable is accessible
    in the system PATH.
    
    Returns:
        True if ffmpeg is available and executable, False otherwise
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            shell=False
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_audio_tracks(video_path: str) -> List[AudioTrackInfo]:
    """
    Get information about all audio tracks in a video file.
    
    Uses ffprobe to extract metadata about audio streams.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        List of AudioTrackInfo objects
        
    Raises:
        FileNotFoundError: If video file doesn't exist
        RuntimeError: If ffprobe fails
    """
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not video_path.is_file():
        raise ValueError(f"Path is not a file: {video_path}")
    
    # Use ffprobe to get audio stream information as JSON
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a",  # Audio streams only
        "-show_entries", "stream=index,codec_name,channels,sample_rate:stream_tags=language",
        "-of", "json",
        str(video_path)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        
        tracks = []
        for stream in streams:
            track = AudioTrackInfo(
                index=stream.get("index", 0),
                codec=stream.get("codec_name", "unknown"),
                channels=stream.get("channels", 2),
                sample_rate=stream.get("sample_rate", 48000),
                language=stream.get("tags", {}).get("language")
            )
            tracks.append(track)
        
        logger.info(f"Found {len(tracks)} audio track(s) in {video_path.name}")
        for track in tracks:
            logger.debug(f"  {track}")
        
        return tracks
        
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed: {e.stderr}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ffprobe output: {e}") from e
    except (OSError, ValueError) as e:
        raise RuntimeError(f"Failed to get audio tracks: {e}") from e


def extract_audio_with_ffmpeg(
    input_video_path: str,
    output_audio_path: str,
    audio_track_index: int = 0,
    target_sample_rate: int = 16000,
    target_channels: int = 1
) -> Path:
    """
    Extract an audio track from a video file using ffmpeg.
    
    Extracts audio to WAV format optimized for Whisper:
    - 16 kHz sample rate (Whisper's native rate)
    - Mono (1 channel)
    - PCM 16-bit signed integer format
    
    Args:
        input_video_path: Path to input video file
        output_audio_path: Path for output WAV file
        audio_track_index: Index of the audio track to extract (default: 0)
        target_sample_rate: Target sample rate in Hz (default: 16000)
        target_channels: Number of channels, 1=mono, 2=stereo (default: 1)
        
    Returns:
        Path object pointing to the extracted audio file
        
    Raises:
        FileNotFoundError: If input video doesn't exist
        RuntimeError: If ffmpeg fails
    """
    input_path = Path(input_video_path).resolve()
    output_path = Path(output_audio_path).resolve()
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")
    
    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Extracting audio track {audio_track_index} from {input_path.name}")
    logger.info(f"  Target format: {target_channels}ch, {target_sample_rate}Hz WAV")
    
    # Build ffmpeg command
    # -i input.mkv: input file
    # -map 0:a:N: select audio track N
    # -ar 16000: resample to 16kHz
    # -ac 1: convert to mono
    # -c:a pcm_s16le: 16-bit PCM format
    # -y: overwrite output file
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-map", f"0:a:{audio_track_index}",  # Select specific audio track
        "-ar", str(target_sample_rate),       # Sample rate
        "-ac", str(target_channels),          # Channels
        "-c:a", "pcm_s16le",                  # Codec
        "-y",                                  # Overwrite
        str(output_path)
    ]
    
    try:
        # Run ffmpeg with minimal output
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if not output_path.exists():
            raise RuntimeError("ffmpeg completed but output file not found")
        
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(f"Audio extracted successfully: {output_path.name} ({file_size_mb:.1f} MB)")
        
        return output_path
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        raise RuntimeError(f"ffmpeg extraction failed: {error_msg}") from e


def find_japanese_audio_track(video_path: str) -> Optional[int]:
    """
    Attempt to find the Japanese audio track automatically.
    
    Looks for tracks with language metadata set to 'jpn', 'ja', or 'japanese'.
    If no language metadata is found, returns None (caller should use default).
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Index of the Japanese track, or None if not found/uncertain
    """
    try:
        tracks = get_audio_tracks(video_path)

        # Look for Japanese language codes (audio-order index, not global stream index)
        japanese_codes = {"jpn", "ja", "japanese"}

        for audio_order, track in enumerate(tracks):
            if track.language and track.language.lower() in japanese_codes:
                # Return position within audio streams for -map 0:a:N
                logger.info(f"Found Japanese audio track at audio-order index {audio_order} (stream index {track.index})")
                return audio_order

        logger.warning("No explicitly marked Japanese audio track found, using default (0)")
        return None

    except (RuntimeError, FileNotFoundError, ValueError, OSError) as e:
        logger.warning(f"Failed to detect Japanese audio track: {e}")
        return None


def mux_subtitle_to_video(
    input_video_path: str,
    subtitle_path: str,
    output_video_path: str,
    subtitle_language: str = "eng",
    subtitle_title: str = "English"
) -> Path:
    """
    Mux an SRT subtitle file into a video file.
    
    Creates a new video file with all original streams plus the subtitle track.
    Uses stream copy for video/audio (no re-encoding).
    
    Args:
        input_video_path: Path to original video file
        subtitle_path: Path to SRT subtitle file
        output_video_path: Path for output video with subtitles
        subtitle_language: ISO 639-2 language code (e.g., "eng", "jpn")
        subtitle_title: Human-readable subtitle track title
        
    Returns:
        Path object pointing to the output video file
        
    Raises:
        FileNotFoundError: If input files don't exist
        RuntimeError: If ffmpeg fails
    """
    input_video = Path(input_video_path).resolve()
    subtitle = Path(subtitle_path).resolve()
    output_video = Path(output_video_path).resolve()
    
    # Validate input files
    for path, name in [(input_video, "Input video"), (subtitle, "Subtitle file")]:
        if not path.exists():
            raise FileNotFoundError(f"{name} not found: {path}")
        if not path.is_file():
            raise ValueError(f"{name} path is not a file: {path}")
    
    output_video.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Muxing subtitle into {input_video.name}")
    
    # Build ffmpeg command
    # -i video.mkv: input video
    # -i subs.srt: input subtitle
    # -c copy: copy all streams without re-encoding
    # -c:s srt: subtitle codec
    # -metadata:s:s:0 language=eng: set subtitle language
    # -metadata:s:s:0 title="English": set subtitle title
    cmd = [
        "ffmpeg",
        "-i", str(input_video),
        "-i", str(subtitle),
        "-map", "0",                                     # All streams from video
        "-map", "1",                                     # Subtitle from srt input
        "-c", "copy",                                    # Copy all streams without re-encoding
        "-c:s", "srt",                                   # Subtitle codec
        "-metadata:s:s:0", f"language={subtitle_language}",
        "-metadata:s:s:0", f"title={subtitle_title}",
        "-y",                                            # Overwrite
        str(output_video)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if not output_video.exists():
            raise RuntimeError("ffmpeg completed but output file not found")
        
        file_size_mb = output_video.stat().st_size / (1024 * 1024)
        logger.info(f"Muxing complete: {output_video.name} ({file_size_mb:.1f} MB)")
        
        return output_video
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        raise RuntimeError(f"ffmpeg muxing failed: {error_msg}") from e
