"""Subtitle candidate comparison utilities — re-exported from core.benchmark."""

from core.benchmark import (  # noqa: F401
    compute_overlap,
    align_segments,
    compute_metrics,
    compare_candidates,
)

__all__ = [
    "compute_overlap",
    "align_segments",
    "compute_metrics",
    "compare_candidates",
]
