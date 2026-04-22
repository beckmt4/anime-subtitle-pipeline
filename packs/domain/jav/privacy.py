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

from typing import Any, Dict

#: Keys whose values should be redacted from metadata dicts.
_REDACTED_KEYS: frozenset[str] = frozenset({
    "file",
    "file_path",
    "video_path",
    "input_path",
    "output_path",
    "source",
    "origin_stream",
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
    return {
        k: "<redacted>" if k in _REDACTED_KEYS else v
        for k, v in meta.items()
    }


__all__ = [
    "ContentGateError",
    "assert_opt_in",
    "redact_metadata",
]
