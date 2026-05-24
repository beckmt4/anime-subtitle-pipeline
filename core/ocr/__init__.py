"""core.ocr — bitmap subtitle OCR interfaces and factory helpers."""

from __future__ import annotations

import importlib
import inspect
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from core.subtitles import SubtitleCandidate

if TYPE_CHECKING:
    from core.runtime.config import Config

logger = logging.getLogger(__name__)


class OCRBackend(ABC):
    """Abstract base class for bitmap subtitle OCR engines.

    Implementors live in language packs or external plugins, not in ``core``.
    """

    @abstractmethod
    def extract(
        self,
        video_path: str,
        stream_index: int,
        language_hint: str | None = None,
    ) -> "SubtitleCandidate":
        """Convert a bitmap subtitle stream to a SubtitleCandidate.

        Parameters
        ----------
        video_path:
            Absolute path to the source video file.
        stream_index:
            Stream index of the bitmap subtitle track inside the container.
        language_hint:
            Optional ISO-639-1 source language code to guide the OCR model.

        Returns
        -------
        SubtitleCandidate
            Extracted segments with ``meta["ocr_confidence"]`` set per segment.
        """


def _resolve_backend_class(spec: str) -> type[OCRBackend]:
    if ":" in spec:
        module_name, class_name = spec.split(":", 1)
    elif "." in spec:
        module_name, class_name = spec.rsplit(".", 1)
    else:
        raise ValueError(
            "OCR backend must be '<module>:<Class>' or '<module>.<Class>'"
        )

    module = importlib.import_module(module_name)
    backend_cls: Any = getattr(module, class_name)
    if not inspect.isclass(backend_cls):
        raise TypeError(f"OCR backend target '{spec}' is not a class")
    if not issubclass(backend_cls, OCRBackend):
        raise TypeError(
            f"OCR backend '{spec}' must inherit from core.ocr.OCRBackend"
        )
    return backend_cls


def create_backend(cfg: "Config") -> OCRBackend | None:
    """Create OCR backend from config, or return None when unavailable."""
    if not bool(cfg.get("ocr", "enabled", default=False)):
        return None

    spec = str(cfg.get("ocr", "backend", default="")).strip()
    if not spec:
        logger.warning(
            "OCR is enabled but ocr.backend is empty; bitmap OCR sources will be skipped"
        )
        return None

    language_models = cfg.get("ocr", "language_models", default={}) or {}
    confidence_warn_below = float(
        cfg.get("ocr", "confidence_warn_below", default=0.70)
    )

    try:
        backend_cls = _resolve_backend_class(spec)
    except Exception as exc:
        logger.warning("Failed to resolve OCR backend '%s': %s", spec, exc)
        return None

    ctor_kwargs: dict[str, Any] = {
        "config": cfg,
        "language_models": language_models,
        "confidence_warn_below": confidence_warn_below,
    }
    try:
        signature = inspect.signature(backend_cls.__init__)
        accepts_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )
        if accepts_kwargs:
            init_kwargs = ctor_kwargs
        else:
            init_kwargs = {
                key: value
                for key, value in ctor_kwargs.items()
                if key in signature.parameters
            }
        try:
            backend = backend_cls(**init_kwargs)
        except TypeError:
            if init_kwargs:
                backend = backend_cls()
            else:
                raise
    except Exception as exc:
        logger.warning("Failed to initialize OCR backend '%s': %s", spec, exc)
        return None

    logger.info("OCR backend initialized: %s", spec)
    return backend


def ocr_subtitle_track(
    video_path: str,
    stream_index: int,
    backend: OCRBackend,
    *,
    language_hint: str | None = None,
    low_confidence_threshold: float = 0.70,
) -> SubtitleCandidate:
    """Extract a bitmap subtitle stream via a swappable OCR backend."""
    candidate = backend.extract(video_path, stream_index, language_hint=language_hint)
    if not isinstance(candidate, SubtitleCandidate):
        raise TypeError("OCR backend must return SubtitleCandidate")

    low_confidence_count = 0
    confidence_values: list[float] = []

    for seg in candidate.segments:
        raw = seg.meta.get("ocr_confidence")
        if raw is None:
            raw = candidate.meta.get("ocr_confidence")
        try:
            conf = float(raw)
        except (TypeError, ValueError):
            conf = 0.0
        seg.meta["ocr_confidence"] = conf
        confidence_values.append(conf)
        if conf < low_confidence_threshold:
            low_confidence_count += 1

    seg_count = len(candidate.segments)
    avg_confidence = round(sum(confidence_values) / seg_count, 4) if seg_count else 0.0
    low_ratio = round(low_confidence_count / seg_count, 4) if seg_count else 0.0

    candidate.meta.setdefault("ocr", {})
    candidate.meta["ocr"].update({
        "segment_count": seg_count,
        "low_confidence_threshold": low_confidence_threshold,
        "low_confidence_segment_count": low_confidence_count,
        "low_confidence_ratio": low_ratio,
        "average_confidence": avg_confidence,
    })
    candidate.meta["ocr_average_confidence"] = avg_confidence
    candidate.meta["ocr_low_confidence_segment_count"] = low_confidence_count

    return candidate


__all__ = ["OCRBackend", "create_backend", "ocr_subtitle_track"]
