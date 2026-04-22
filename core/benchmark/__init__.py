"""core.benchmark — candidate comparison and quality metrics.

Measures subtitle quality by comparing candidates to a reference using
WER, BLEU, and chrF.  Generates comparison JSON and (planned) HTML reports.

Public API (target — populated as files migrate from root)
----------------------------------------------------------
run_benchmark(media, cfg)          → dict   full benchmark result
compute_metrics(ref, hyp)          → dict   WER / BLEU / chrF
align_segments(ref_segs, hyp_segs) → list   temporally aligned pairs

During the migration period the root-level ``benchmark.py`` and
``compare_core.py`` own the implementation.  Import from there until the
migration is complete.
"""

from __future__ import annotations

from compare_core import compute_metrics, align_segments  # noqa: F401

__all__ = [
    "compute_metrics",
    "align_segments",
]
