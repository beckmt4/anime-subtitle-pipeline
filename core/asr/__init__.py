"""core.asr — speech → text backend abstraction.

Converts a WAV audio file to a timestamped SubtitleCandidate.

The abstract ``ASRBackend`` interface allows the runtime to swap engines
(e.g., Faster-Whisper, whisper.cpp, AssemblyAI) without touching pipeline
logic.  Language-specific segmentation post-processing and vocabulary hints
belong in language packs, not here.

Public API
----------
ASRBackend                            Abstract base class.
FasterWhisperASR                      Concrete Faster-Whisper implementation.
build_candidate_from_segments(…)      Helper — wraps raw ASR output.
transcribe_audio_to_candidate(…)      One-shot convenience function.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.subtitles import SubtitleCandidate


class ASRBackend(ABC):
    """Abstract interface for all ASR engine adapters.

    Concrete implementations live in core or language pack–specific modules.
    Core orchestration code must only depend on this interface.
    """

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> "SubtitleCandidate":
        """Transcribe audio to a SubtitleCandidate.

        Parameters
        ----------
        audio_path:
            Absolute path to a WAV file (16 kHz, mono recommended).
        language:
            Optional ISO-639-1 hint.  ``None`` means auto-detect.

        Returns
        -------
        SubtitleCandidate
            Transcribed segments.  ``candidate.language`` is set to the
            detected or supplied language code.
        """

    @abstractmethod
    def load(self) -> None:
        """Pre-load model weights into memory."""

    @abstractmethod
    def unload(self) -> None:
        """Release model weights from memory."""

import logging

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

from config import Config
from core.subtitles import Segment as GenericSegment  # SubtitleCandidate already imported above

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
    segment: GenericSegment,
    *,
    previous: Optional[GenericSegment],
    repeated_count: int,
    language: str,
    thresholds: Dict[str, Any],
) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    duration = segment.duration
    text = segment.text.strip()
    asr_meta = segment.meta.get("asr", {})

    no_speech = asr_meta.get("no_speech_prob", getattr(segment, "no_speech_prob", None))
    if no_speech is not None and no_speech > thresholds["warn_no_speech_prob_above"]:
        warnings.append(_warning(
            "high_no_speech_probability",
            f"no_speech_prob {no_speech:.2f} > {thresholds['warn_no_speech_prob_above']:.2f}",
        ))

    avg_logprob = asr_meta.get("avg_logprob", getattr(segment, "avg_logprob", None))
    if avg_logprob is not None and avg_logprob < thresholds["warn_avg_logprob_below"]:
        warnings.append(_warning(
            "low_average_log_probability",
            f"avg_logprob {avg_logprob:.2f} < {thresholds['warn_avg_logprob_below']:.2f}",
        ))

    compression = asr_meta.get("compression_ratio", getattr(segment, "compression_ratio", None))
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
    ) -> Tuple[List[GenericSegment], SubtitleCandidate]:
        """
        Transcribe an audio file to Japanese text segments with timestamps.

        Args:
            audio_path: Path to audio file (WAV format recommended)
            language: Language code (default: from config, typically "ja")

        Returns:
            A tuple of (segments, candidate) where segments is a list of
            generic subtitle Segment objects
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
            
            # Convert iterator to list of generic Segment objects
            segments = []
            for seg in segments_iter:
                # Filter out segments with no speech
                text = seg.text.strip()
                if not text:
                    continue
                
                segment = GenericSegment(
                    start=seg.start,
                    end=seg.end,
                    text=text,
                    meta={
                        "asr": {
                            "avg_logprob": getattr(seg, "avg_logprob", None),
                            "no_speech_prob": getattr(seg, "no_speech_prob", None),
                            "compression_ratio": getattr(seg, "compression_ratio", None),
                        },
                    },
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

        Loads the audio at *audio_path* into a float32 PCM array via
        ``faster_whisper.audio.decode_audio`` and passes it to the Whisper
        model's language detector.  ``WhisperModel.detect_language`` expects a
        NumPy array — passing a raw file-path string causes
        ``AttributeError: 'str' object has no attribute 'dtype'``.

        Loads the model if needed. Call unload_model() when done if you
        don't plan to transcribe immediately after.

        Returns:
            (language_code, probability) — e.g. ("ja", 0.97)
        """
        self.load_model()
        audio = decode_audio(str(audio_path), sampling_rate=16000)
        lang, prob, _ = self.model.detect_language(audio)
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

    def _build_candidate_from_segments(self, segments: List[GenericSegment], language: str, origin_stream: str) -> SubtitleCandidate:
        """Build a SubtitleCandidate from ASR segments."""
        return build_candidate_from_segments(
            segments,
            self.config,
            candidate_id=f"asr_{language}",
            language=language,
            origin_stream=origin_stream,
        )


def transcribe_audio_to_segments(audio_path: str, config: Config) -> List[GenericSegment]:
    """
    Convenience function for one-shot transcription.
    
    Creates an ASR instance, transcribes the audio, and returns segments.
    Model is automatically unloaded after transcription.
    
    Args:
        audio_path: Path to audio file
        config: Configuration object
        
    Returns:
        List of generic Segment objects with Japanese transcriptions
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
    
    def transcribe(self, audio_path: str) -> List[GenericSegment]:
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
    segments: List[GenericSegment],
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
        key = " ".join(s.text.casefold().split())
        if key:
            text_counts[key] = text_counts.get(key, 0) + 1

    generic_segments: List[GenericSegment] = []
    warning_count = 0
    low_confidence_count = 0
    previous: Optional[GenericSegment] = None
    for s in segments:
        key = " ".join(s.text.casefold().split())
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

        base_asr_meta = dict(getattr(s, "meta", {}).get("asr", {}))
        asr_meta = {
            "avg_logprob": base_asr_meta.get("avg_logprob", getattr(s, "avg_logprob", None)),
            "no_speech_prob": base_asr_meta.get("no_speech_prob", getattr(s, "no_speech_prob", None)),
            "compression_ratio": base_asr_meta.get("compression_ratio", getattr(s, "compression_ratio", None)),
            "low_confidence": low_confidence,
            "warnings": warnings,
        }
        segment_meta = {**getattr(s, "meta", {}), "asr": {**base_asr_meta, **asr_meta}}
        generic_segments.append(GenericSegment(s.start, s.end, s.text, meta=segment_meta))

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
    "FasterWhisperASR",
    "BatchASR",
    "build_candidate_from_segments",
    "transcribe_audio_to_candidate",
]
