"""core.artifacts — processing ledger and artifact storage.

Status: **not yet implemented** (Issue #18).

Planned responsibilities
------------------------
- SQLite-backed processing ledger: tracks which files have been processed
  and with what outcomes.
- Subtitle candidate versioning: stores SubtitleCandidate objects keyed by
  (media_hash, source_id, model_version).
- Benchmark run storage: retains metric snapshots for regression comparison.
- Re-processing records: supports explicit re-queue with recorded reason.

Planned public API
------------------
ArtifactRegistry              Main facade for all storage operations.
ProcessingLedger              Ledger of processed files and outcomes.
store_candidate(…)            Persist a SubtitleCandidate with metadata.
get_candidate(…)              Retrieve a previously stored candidate.
record_benchmark_run(…)       Save a benchmark result set.
"""

from __future__ import annotations

__all__: list = []  # Empty until Issue #18 is implemented.
