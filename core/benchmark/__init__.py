"""core.benchmark — candidate comparison and quality metrics.

Measures subtitle quality by comparing candidates to a reference using
WER, BLEU, and chrF.
Implementation lives in ``core.benchmark.compare_core``.
The root-level ``compare_core.py`` is a re-export shim pointing here.

Public API
----------
compute_metrics(ref_texts, cand_texts) → dict   WER / BLEU / chrF
align_segments(ref, cand)              → list   temporally aligned pairs
compare_candidates(ref, cand)          → dict   full comparison report
compute_overlap(seg1, seg2)            → float
build_scorecards(results)              → list   per-candidate scorecards
render_html_report(results, path)      → str    self-contained HTML report
"""

from core.benchmark.compare_core import (  # noqa: F401
    compute_overlap,
    align_segments,
    compute_metrics,
    compare_candidates,
)
from core.benchmark.html_report import (  # noqa: F401
    build_scorecards,
    render_html_report,
)

__all__ = [
    "align_segments",
    "compute_metrics",
    "compare_candidates",
    "compute_overlap",
    "build_scorecards",
    "render_html_report",
]
