"""JAV domain privacy controls, logging redaction, and content gate.

This module enforces the privacy and content gating requirements for the JAV
domain pack.  It is injected by ``core.runtime`` before any pipeline step
executes when the active domain pack is ``jav``.

Key responsibilities
--------------------
- Verify that the adult content opt-in flag is set before allowing any
  processing (``assert_opt_in``).
- Redact file paths and metadata from structured log outputs so that
  personally identifying or privacy-sensitive filenames do not appear in
  logs, benchmark results, or artifact records.
- Provide a redacted copy of a metadata dict for safe storage.

Usage
-----
>>> from packs.domain.jav.privacy import assert_opt_in, redact_metadata
>>> assert_opt_in(opt_in=True)    # raises if False
>>> safe = redact_metadata({"file": "/path/to/video.mp4", "duration": 90.0})
>>> safe["file"]
'<redacted>'
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

#: Keys whose values should be redacted from metadata dicts.
_REDACTED_METADATA_KEYS: frozenset[str] = frozenset({
    "file",
    "file_path",
    "video_path",
    "input_path",
    "output_path",
    "qc_json",
    "origin_stream",
})

_REDACTED_REPORT_KEYS: frozenset[str] = frozenset({
    "video",
    "planned_output_srt",
    "output_srt",
    "qc_json",
    "review_ui_output",
})


class ContentGateError(RuntimeError):
    """Raised when adult-content processing is attempted without opt-in."""


def assert_opt_in(opt_in: bool) -> None:
    """Assert that the adult-content opt-in flag is ``True``.

    Parameters
    ----------
    opt_in:
        Value of the ``adult_content_opt_in`` config flag.

    Raises
    ------
    ContentGateError
        If *opt_in* is ``False``.
    """
    if not opt_in:
        raise ContentGateError(
            "JAV domain pack requires explicit opt-in. "
            "Set 'domain.adult_content_opt_in: true' in your config.yaml."
        )


def _redact_value(key: str | None, value: Any, *, report_mode: bool) -> Any:
    if isinstance(value, Mapping):
        return {
            str(child_key): _redact_value(str(child_key), child_value, report_mode=report_mode)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(None, child, report_mode=report_mode) for child in value]
    if key in _REDACTED_METADATA_KEYS:
        return "<redacted>"
    if report_mode and key in _REDACTED_REPORT_KEYS:
        return "<redacted>"
    if report_mode and key == "stream" and isinstance(value, str) and value.startswith("sidecar:"):
        return "sidecar:<redacted>"
    return value


def redact_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *meta* with privacy-sensitive values replaced.

    Parameters
    ----------
    meta:
        Original metadata dict (e.g. SubtitleCandidate.meta).

    Returns
    -------
    dict
        New dict where values for keys in ``_REDACTED_KEYS`` are replaced
        with the string ``'<redacted>'``.
    """
    return _redact_value(None, meta, report_mode=False)


def redact_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Return a redacted copy of a report/log payload.

    This is intended for user-facing generate/inspect metadata, selection
    reports, and other structured outputs where stream labels like
    ``sidecar:movie.en.srt`` should be scrubbed without losing source labels.
    """
    return _redact_value(None, report, report_mode=True)


__all__ = [
    "ContentGateError",
    "assert_opt_in",
    "redact_metadata",
    "redact_report",
]
