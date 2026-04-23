"""core.artifacts.ledger — ProcessingLedger: query-oriented view of the registry.

The :class:`ProcessingLedger` wraps an :class:`~core.artifacts.registry.ArtifactRegistry`
and provides higher-level reporting queries such as "which media files have
been processed?", "what was the last accepted candidate for this media?", and
"how many candidates are awaiting review?".
"""

from __future__ import annotations

from typing import Dict, List, Optional

from core.artifacts.models import (
    BenchmarkRunRecord,
    CANDIDATE_STATUS_ACCEPTED,
    CANDIDATE_STATUS_FAILED,
    CANDIDATE_STATUS_REVIEW_REQUIRED,
    ReviewTaskRecord,
    REVIEW_STATUS_PENDING,
    SubtitleCandidateRecord,
)
from core.artifacts.registry import ArtifactRegistry


class ProcessingLedger:
    """Read-oriented view over the artifact registry.

    Args:
        registry: An open :class:`~core.artifacts.registry.ArtifactRegistry` instance.
    """

    def __init__(self, registry: ArtifactRegistry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------
    # High-level status queries
    # ------------------------------------------------------------------

    def processed_media_hashes(self) -> List[str]:
        """Return the ``media_hash`` of every tracked media file."""
        return [a.media_hash for a in self._registry.list_media_assets()]

    def is_processed(self, media_hash: str) -> bool:
        """Return ``True`` if *media_hash* has at least one stored candidate."""
        candidates = self._registry.list_candidates(media_hash)
        return len(candidates) > 0

    def accepted_candidates(self, media_hash: str) -> List[SubtitleCandidateRecord]:
        """Return all *accepted* candidates for *media_hash*."""
        return self._registry.list_candidates(media_hash, status=CANDIDATE_STATUS_ACCEPTED)

    def failed_candidates(self, media_hash: str) -> List[SubtitleCandidateRecord]:
        """Return all *failed* candidates for *media_hash*."""
        return self._registry.list_candidates(media_hash, status=CANDIDATE_STATUS_FAILED)

    def review_required_candidates(self, media_hash: str) -> List[SubtitleCandidateRecord]:
        """Return all *review_required* candidates for *media_hash*."""
        return self._registry.list_candidates(
            media_hash, status=CANDIDATE_STATUS_REVIEW_REQUIRED
        )

    def pending_review_tasks(self) -> List[ReviewTaskRecord]:
        """Return all review tasks with status ``'pending'``."""
        return self._registry.list_review_tasks(status=REVIEW_STATUS_PENDING)

    # ------------------------------------------------------------------
    # Benchmark summaries
    # ------------------------------------------------------------------

    def latest_benchmark_run(self, media_hash: str) -> Optional[BenchmarkRunRecord]:
        """Return the most recently created benchmark run for *media_hash*, or ``None``."""
        runs = self._registry.list_benchmark_runs(media_hash)
        return runs[-1] if runs else None

    def benchmark_summary(self, media_hash: str) -> Dict[str, object]:
        """Return a dict summarising benchmark runs for *media_hash*.

        Keys: ``run_count``, ``best_wer``, ``best_bleu``, ``best_chrf``.
        All metric values are ``None`` when no runs exist.
        """
        runs = self._registry.list_benchmark_runs(media_hash)
        if not runs:
            return {"run_count": 0, "best_wer": None, "best_bleu": None, "best_chrf": None}
        wers = [r.wer for r in runs if r.wer is not None]
        bleus = [r.bleu for r in runs if r.bleu is not None]
        chrfs = [r.chrf for r in runs if r.chrf is not None]
        return {
            "run_count": len(runs),
            "best_wer": min(wers) if wers else None,   # lower is better
            "best_bleu": max(bleus) if bleus else None,  # higher is better
            "best_chrf": max(chrfs) if chrfs else None,  # higher is better
        }

    # ------------------------------------------------------------------
    # Reprocess helpers
    # ------------------------------------------------------------------

    def reprocess_candidates(self, media_hash: str) -> List[SubtitleCandidateRecord]:
        """Return all candidates that are linked to a 'reprocess' review task."""
        tasks = self._registry.list_review_tasks(media_hash, status="reprocess")
        result = []
        for task in tasks:
            cand = self._registry.get_candidate(task.candidate_id)
            if cand is not None:
                result.append(cand)
        return result


__all__ = ["ProcessingLedger"]
