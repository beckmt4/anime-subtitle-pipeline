"""
Automatic Speech Recognition using Faster-Whisper.

This module handles Japanese audio transcription using the Faster-Whisper
implementation of OpenAI's Whisper model with CTranslate2 backend.

Key features:
- Whisper Large V3 Turbo model for high-quality Japanese transcription
- GPU acceleration with automatic fallback to CPU
- Configurable quantization for memory-constrained environments
- Voice Activity Detection (VAD) to filter silence
- Returns timestamped segments for subtitle generation
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from faster_whisper import WhisperModel

from config import Config
from models import Segment as GenericSegment, SubtitleCandidate

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    """
    A transcribed audio segment with timing information.
    
    This is the core data structure passed through the pipeline.
    Additional fields (text_en_raw, text_en_final) are added by later stages.
    """
    start: float           # Start time in seconds
    end: float             # End time in seconds
    text_ja: str           # Japanese transcription
    text_en_raw: str = ""  # Raw English translation (from MT)
    text_en_final: str = "" # Polished English (from LLM or same as raw)
    
    _REPR_TEXT_MAX_LEN = 30  # Maximum text length in repr
    
    @property
    def duration(self) -> float:
        """Duration of the segment in seconds."""
        return self.end - self.start
    
    def __repr__(self) -> str:
        text_preview = self.text_ja[:self._REPR_TEXT_MAX_LEN]
        return f"Segment({self.start:.2f}-{self.end:.2f}s: '{text_preview}...')"


class FasterWhisperASR:
    """
    Japanese ASR using Faster-Whisper.
    
    This class wraps the Faster-Whisper library and provides a simple interface
    for transcribing Japanese audio to timestamped text segments.
    """
    
    def __init__(self, config: Config):
        """
        Initialize the Faster-Whisper ASR model.
        
        Args:
            config: Configuration object with ASR settings
        """
        self.config = config
        self.model: Optional[WhisperModel] = None
        
        logger.info("Initializing Faster-Whisper ASR")
        logger.info(f"  Model: {config.asr_model_name}")
        logger.info(f"  Device: {config.asr_device}")
        logger.info(f"  Compute type: {config.asr_compute_type}")
        logger.info(f"  Batch size: {config.asr_batch_size}")
    
    def load_model(self) -> None:
        """
        Load the Whisper model.
        
        This is separated from __init__ to allow lazy loading and
        to provide better error handling for model download/loading.
        On first run, this will download the model from Hugging Face.
        
        Raises:
            RuntimeError: If model loading fails
        """
        if self.model is not None:
            logger.debug("Model already loaded")
            return
        
        logger.info("Loading Whisper model (this may download the model on first run)...")
        
        try:
            self.model = WhisperModel(
                model_size_or_path=self.config.asr_model_name,
                device=self.config.asr_device,
                compute_type=self.config.asr_compute_type,
                # Use local files only after first download
                local_files_only=False
            )
            logger.info("Model loaded successfully")
            
        except (OSError, ValueError, RuntimeError) as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise RuntimeError(f"Could not load Whisper model: {e}") from e
    
    def transcribe_audio_to_segments(
        self,
        audio_path: str,
        language: Optional[str] = None
    ) -> List[Segment]:
        """
        Transcribe an audio file to Japanese text segments with timestamps.
        
        Args:
            audio_path: Path to audio file (WAV format recommended)
            language: Language code (default: from config, typically "ja")
            
        Returns:
            List of Segment objects with Japanese transcriptions and timing
            
        Raises:
            FileNotFoundError: If audio file doesn't exist
            RuntimeError: If transcription fails
        """
        audio_path = Path(audio_path).resolve()
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if not audio_path.is_file():
            raise ValueError(f"Path is not a file: {audio_path}")
        
        # Ensure model is loaded
        self.load_model()
        
        language = language or self.config.asr_language
        
        logger.info(f"Transcribing {audio_path.name}")
        logger.info(f"  Language: {language}")
        logger.info(f"  VAD filter: {self.config.asr_vad_filter}")
        
        try:
            # Configure transcription parameters
            vad_parameters = None
            if self.config.asr_vad_filter:
                vad_parameters = self.config.get("asr", "vad_parameters", default={})
            
            # Run transcription
            segments_iter, info = self.model.transcribe(
                str(audio_path),
                language=language,
                task="transcribe",  # Not "translate" - we want Japanese output
                beam_size=self.config.asr_beam_size,
                vad_filter=self.config.asr_vad_filter,
                vad_parameters=vad_parameters,
                # batch_size is used internally by faster-whisper
            )
            
            # Log detected language and duration
            logger.info(f"Detected language: {info.language} (probability: {info.language_probability:.2f})")
            logger.info(f"Audio duration: {info.duration:.2f}s")
            
            # Convert iterator to list of Segment objects
            segments = []
            for seg in segments_iter:
                # Filter out segments with no speech
                text = seg.text.strip()
                if not text:
                    continue
                
                segment = Segment(
                    start=seg.start,
                    end=seg.end,
                    text_ja=text
                )
                segments.append(segment)
            
            logger.info(f"Transcription complete: {len(segments)} segments")
            
            if not segments:
                logger.warning("No speech detected in audio file")
            
            # Build and store a generic SubtitleCandidate for new pipeline usage
            self.last_candidate = self._build_candidate_from_segments(
                segments,
                language=language or "ja",
                origin_stream="audio:0",
            )
            return segments
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Failed to transcribe audio: {e}") from e
    
    def unload_model(self) -> None:
        """
        Unload the model to free memory.
        
        Useful when processing multiple files sequentially or
        when switching to a different model. Sets the model reference
        to None, allowing Python's garbage collector to free the memory.
        """
        if self.model is not None:
            logger.debug("Unloading Whisper model")
            self.model = None


def transcribe_audio_to_segments(audio_path: str, config: Config) -> List[Segment]:
    """
    Convenience function for one-shot transcription.
    
    Creates an ASR instance, transcribes the audio, and returns segments.
    Model is automatically unloaded after transcription.
    
    Args:
        audio_path: Path to audio file
        config: Configuration object
        
    Returns:
        List of Segment objects with Japanese transcriptions
    """
    asr = FasterWhisperASR(config)
    segments = asr.transcribe_audio_to_segments(audio_path)
    asr.unload_model()
    return segments


# Alternative: Keep model loaded for batch processing
class BatchASR:
    """
    ASR processor that keeps the model loaded for multiple files.
    
    Usage:
        with BatchASR(config) as asr:
            for audio_file in audio_files:
                segments = asr.transcribe(audio_file)
                # process segments...
    """
    
    def __init__(self, config: Config):
        self.asr = FasterWhisperASR(config)
    
    def __enter__(self):
        self.asr.load_model()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.asr.unload_model()
        return False
    
    def transcribe(self, audio_path: str) -> List[Segment]:
        """Transcribe an audio file."""
        return self.asr.transcribe_audio_to_segments(audio_path)

    def candidate(self) -> Optional[SubtitleCandidate]:
        """Return the last built SubtitleCandidate (if available)."""
        return getattr(self.asr, "last_candidate", None)


# ---------------------------------------------------------------------------
# New generic candidate builder utilities
# ---------------------------------------------------------------------------
def build_candidate_from_segments(
    segments: List[Segment],
    config: Config,
    candidate_id: str = "asr_ja",
    language: str = "ja",
    origin_stream: str = "audio:0",
) -> SubtitleCandidate:
    """Create a generic SubtitleCandidate from legacy ASR segments.

    This preserves backwards compatibility while enabling downstream
    multi-track logic to operate on a unified structure.
    """
    generic_segments = [
        GenericSegment(s.start, s.end, s.text_ja) for s in segments
    ]
    meta = {
        "asr_model": config.asr_model_name,
        "compute_type": config.asr_compute_type,
        "beam_size": config.asr_beam_size,
        "vad_filter": config.asr_vad_filter,
    }
    return SubtitleCandidate(
        id=candidate_id,
        language=language,
        source="asr",
        origin_stream=origin_stream,
        segments=generic_segments,
        meta=meta,
    )


def transcribe_audio_to_candidate(
    audio_path: str,
    config: Config,
    language: Optional[str] = None,
    origin_stream: str = "audio:0",
) -> SubtitleCandidate:
    """One-shot convenience returning a SubtitleCandidate instead of segments."""
    asr = FasterWhisperASR(config)
    segments = asr.transcribe_audio_to_segments(audio_path, language=language)
    # last_candidate already built inside transcribe; just ensure origin_stream override if provided
    cand = getattr(asr, "last_candidate", None)
    if cand and cand.origin_stream != origin_stream:
        cand.origin_stream = origin_stream
    asr.unload_model()
    return cand if cand else build_candidate_from_segments(
        segments,
        config,
        candidate_id="asr_ja",
        language=language or "ja",
        origin_stream=origin_stream,
    )


# Internal method added to class dynamically (kept outside to avoid clutter in main body)
def _build_candidate_from_segments(self, segments: List[Segment], language: str, origin_stream: str) -> SubtitleCandidate:
    return build_candidate_from_segments(
        segments,
        self.config,
        candidate_id=f"asr_{language}",
        language=language,
        origin_stream=origin_stream,
    )

# Attach helper to class
setattr(FasterWhisperASR, "_build_candidate_from_segments", _build_candidate_from_segments)

__all__ = [
    "Segment",
    "FasterWhisperASR",
    "BatchASR",
    "build_candidate_from_segments",
    "transcribe_audio_to_candidate",
]
