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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from faster_whisper import WhisperModel

from config import Config
from models import Segment as GenericSegment, SubtitleCandidate

logger = logging.getLogger(__name__)


_JAPANESE_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


def _quality_thresholds(config: Config) -> Dict[str, Any]:
    """Return ASR quality thresholds with conservative defaults."""
    raw = config.get("asr", "quality", default={}) or {}
    return {
        "warn_no_speech_prob_above": raw.get("warn_no_speech_prob_above", 0.60),
        "warn_avg_logprob_below": raw.get("warn_avg_logprob_below", -1.00),
        "warn_compression_ratio_above": raw.get("warn_compression_ratio_above", 2.40),
        "warn_min_duration_sec": raw.get("warn_min_duration_sec", 0.25),
        "warn_max_duration_sec": raw.get("warn_max_duration_sec", 12.0),
        "warn_gap_sec": raw.get("warn_gap_sec", 6.0),
        "warn_repeated_text_count": raw.get("warn_repeated_text_count", 3),
        "warn_japanese_char_ratio_below": raw.get("warn_japanese_char_ratio_below", 0.20),
        "fail_low_confidence_ratio": raw.get("fail_low_confidence_ratio", 0.50),
    }


def _warning(type_: str, detail: str, severity: str = "warning") -> Dict[str, Any]:
    return {"type": type_, "severity": severity, "detail": detail}


def _japanese_char_ratio(text: str) -> float:
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return 0.0
    return sum(1 for ch in chars if _JAPANESE_CHAR_RE.match(ch)) / len(chars)


def _segment_quality_warnings(
    segment: "Segment",
    *,
    previous: Optional["Segment"],
    repeated_count: int,
    language: str,
    thresholds: Dict[str, Any],
) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    duration = segment.duration
    text = segment.text_ja.strip()

    no_speech = segment.no_speech_prob
    if no_speech is not None and no_speech > thresholds["warn_no_speech_prob_above"]:
        warnings.append(_warning(
            "high_no_speech_probability",
            f"no_speech_prob {no_speech:.2f} > {thresholds['warn_no_speech_prob_above']:.2f}",
        ))

    avg_logprob = segment.avg_logprob
    if avg_logprob is not None and avg_logprob < thresholds["warn_avg_logprob_below"]:
        warnings.append(_warning(
            "low_average_log_probability",
            f"avg_logprob {avg_logprob:.2f} < {thresholds['warn_avg_logprob_below']:.2f}",
        ))

    compression = segment.compression_ratio
    if compression is not None and compression > thresholds["warn_compression_ratio_above"]:
        warnings.append(_warning(
            "high_compression_ratio",
            f"compression_ratio {compression:.2f} > {thresholds['warn_compression_ratio_above']:.2f}",
        ))

    if duration < thresholds["warn_min_duration_sec"]:
        warnings.append(_warning(
            "very_short_segment",
            f"duration {duration:.2f}s < {thresholds['warn_min_duration_sec']:.2f}s",
        ))
    elif duration > thresholds["warn_max_duration_sec"]:
        warnings.append(_warning(
            "very_long_segment",
            f"duration {duration:.2f}s > {thresholds['warn_max_duration_sec']:.2f}s",
        ))

    if previous is not None:
        gap = segment.start - previous.end
        if gap > thresholds["warn_gap_sec"]:
            warnings.append(_warning(
                "long_gap_before_segment",
                f"gap before segment {gap:.2f}s > {thresholds['warn_gap_sec']:.2f}s",
            ))

    if repeated_count >= thresholds["warn_repeated_text_count"]:
        warnings.append(_warning(
            "repeated_text",
            f"text repeats {repeated_count} times in ASR output",
        ))

    if language.startswith("ja") and len(text) >= 3:
        ratio = _japanese_char_ratio(text)
        if ratio < thresholds["warn_japanese_char_ratio_below"]:
            warnings.append(_warning(
                "low_japanese_character_ratio",
                f"Japanese character ratio {ratio:.2f} < {thresholds['warn_japanese_char_ratio_below']:.2f}",
            ))

    return warnings


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
    avg_logprob: Optional[float] = None
    no_speech_prob: Optional[float] = None
    compression_ratio: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    
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
    ) -> Tuple[List[Segment], SubtitleCandidate]:
        """
        Transcribe an audio file to Japanese text segments with timestamps.

        Args:
            audio_path: Path to audio file (WAV format recommended)
            language: Language code (default: from config, typically "ja")

        Returns:
            A tuple of (segments, candidate) where segments is a list of Segment
            objects with Japanese transcriptions and timing, and candidate is the
            corresponding SubtitleCandidate built from those segments.

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
                    text_ja=text,
                    avg_logprob=getattr(seg, "avg_logprob", None),
                    no_speech_prob=getattr(seg, "no_speech_prob", None),
                    compression_ratio=getattr(seg, "compression_ratio", None),
                )
                segments.append(segment)
            
            logger.info(f"Transcription complete: {len(segments)} segments")
            
            if not segments:
                logger.warning("No speech detected in audio file")
            
            candidate = self._build_candidate_from_segments(
                segments,
                language=language or "ja",
                origin_stream="audio:0",
            )
            return segments, candidate
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Failed to transcribe audio: {e}") from e
    
    def detect_language(self, audio_path: str) -> tuple[str, float]:
        """Probe the dominant language of an audio clip.

        Loads the model if needed. Call unload_model() when done if you
        don't plan to transcribe immediately after.

        Returns:
            (language_code, probability) — e.g. ("ja", 0.97)
        """
        self.load_model()
        lang, prob = self.model.detect_language(str(audio_path))
        logger.debug("Language probe: '%s' confidence=%.2f", lang, prob)
        return lang, prob

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

    def _build_candidate_from_segments(self, segments: List[Segment], language: str, origin_stream: str) -> SubtitleCandidate:
        """Build a SubtitleCandidate from legacy ASR Segment list."""
        return build_candidate_from_segments(
            segments,
            self.config,
            candidate_id=f"asr_{language}",
            language=language,
            origin_stream=origin_stream,
        )


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
    segments, _ = asr.transcribe_audio_to_segments(audio_path)
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
        self._last_candidate: Optional[SubtitleCandidate] = None
    
    def __enter__(self):
        self.asr.load_model()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.asr.unload_model()
        return False
    
    def transcribe(self, audio_path: str) -> List[Segment]:
        """Transcribe an audio file."""
        segments, cand = self.asr.transcribe_audio_to_segments(audio_path)
        self._last_candidate = cand
        return segments

    def candidate(self) -> Optional[SubtitleCandidate]:
        """Return the last built SubtitleCandidate (if available)."""
        return self._last_candidate


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
    thresholds = _quality_thresholds(config)
    text_counts: Dict[str, int] = {}
    for s in segments:
        key = " ".join(s.text_ja.casefold().split())
        if key:
            text_counts[key] = text_counts.get(key, 0) + 1

    generic_segments: List[GenericSegment] = []
    warning_count = 0
    low_confidence_count = 0
    previous: Optional[Segment] = None
    for s in segments:
        key = " ".join(s.text_ja.casefold().split())
        warnings = _segment_quality_warnings(
            s,
            previous=previous,
            repeated_count=text_counts.get(key, 0),
            language=language,
            thresholds=thresholds,
        )
        previous = s
        warning_count += len(warnings)
        low_confidence = bool(warnings)
        if low_confidence:
            low_confidence_count += 1

        asr_meta = {
            "avg_logprob": s.avg_logprob,
            "no_speech_prob": s.no_speech_prob,
            "compression_ratio": s.compression_ratio,
            "low_confidence": low_confidence,
            "warnings": warnings,
        }
        segment_meta = {**getattr(s, "meta", {}), "asr": asr_meta}
        generic_segments.append(GenericSegment(s.start, s.end, s.text_ja, meta=segment_meta))

    if not segments:
        summary_status = "fail"
        summary_warnings = [_warning("no_speech_segments", "ASR produced no non-empty speech segments", "error")]
    else:
        low_confidence_ratio = low_confidence_count / len(segments)
        summary_status = "fail" if low_confidence_ratio >= thresholds["fail_low_confidence_ratio"] else (
            "warn" if low_confidence_count else "clean"
        )
        summary_warnings = []

    if summary_status != "clean":
        logger.warning(
            "ASR quality %s: %d/%d low-confidence segment(s), %d warning(s)",
            summary_status,
            low_confidence_count,
            len(segments),
            warning_count,
        )

    asr_quality = {
        "status": summary_status,
        "segment_count": len(segments),
        "low_confidence_segment_count": low_confidence_count,
        "low_confidence_ratio": (
            round(low_confidence_count / len(segments), 4) if segments else 1.0
        ),
        "warning_count": warning_count + len(summary_warnings),
        "summary_warnings": summary_warnings,
        "thresholds": thresholds,
    }
    meta = {
        "asr_model": config.asr_model_name,
        "compute_type": config.asr_compute_type,
        "beam_size": config.asr_beam_size,
        "vad_filter": config.asr_vad_filter,
        "asr_quality": asr_quality,
        "asr_quality_status": summary_status,
        "asr_low_confidence_segment_count": low_confidence_count,
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
    _, cand = asr.transcribe_audio_to_segments(audio_path, language=language)
    if cand.origin_stream != origin_stream:
        cand.origin_stream = origin_stream
    asr.unload_model()
    return cand


__all__ = [
    "Segment",
    "FasterWhisperASR",
    "BatchASR",
    "build_candidate_from_segments",
    "transcribe_audio_to_candidate",
]
