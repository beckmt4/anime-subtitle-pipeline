"""core.artifacts — processing ledger and artifact storage.

Public API
----------
ArtifactRegistry              Main facade for all storage operations.
ProcessingLedger              Read-oriented view over the artifact registry.

Record types
------------
MediaAssetRecord              A tracked media file.
StreamAssetRecord             An individual audio/subtitle/video stream.
SubtitleCandidateRecord       A stored subtitle candidate (versioned by
                              media_hash + source_id + model_version).
BenchmarkRunRecord            A benchmark run result snapshot.
BenchmarkComparisonRecord     A per-metric comparison row within a benchmark run.
ArtifactRecord                A versioned output file (e.g. .srt, .ass).
ReviewTaskRecord              A review task (pending/approved/rejected/reprocess).
StateTransitionRecord         An audit-log entry for a status change.

Status constants
----------------
CANDIDATE_STATUS_PENDING          ``'pending'``
CANDIDATE_STATUS_ACCEPTED         ``'accepted'``
CANDIDATE_STATUS_FAILED           ``'failed'``
CANDIDATE_STATUS_REVIEW_REQUIRED  ``'review_required'``
REVIEW_STATUS_PENDING             ``'pending'``
REVIEW_STATUS_APPROVED            ``'approved'``
REVIEW_STATUS_REJECTED            ``'rejected'``
REVIEW_STATUS_REPROCESS           ``'reprocess'``
ARTIFACT_STATUS_ACTIVE            ``'active'``
ARTIFACT_STATUS_SUPERSEDED        ``'superseded'``
ARTIFACT_STATUS_DELETED           ``'deleted'``
"""

from __future__ import annotations

from core.artifacts.ledger import ProcessingLedger
from core.artifacts.models import (
    ArtifactRecord,
    ARTIFACT_STATUS_ACTIVE,
    ARTIFACT_STATUS_DELETED,
    ARTIFACT_STATUS_SUPERSEDED,
    ARTIFACT_STATUSES,
    BenchmarkComparisonRecord,
    BenchmarkRunRecord,
    CANDIDATE_STATUS_ACCEPTED,
    CANDIDATE_STATUS_FAILED,
    CANDIDATE_STATUS_PENDING,
    CANDIDATE_STATUS_REVIEW_REQUIRED,
    CANDIDATE_STATUSES,
    MediaAssetRecord,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_REJECTED,
    REVIEW_STATUS_REPROCESS,
    REVIEW_STATUSES,
    ReviewTaskRecord,
    StateTransitionRecord,
    StreamAssetRecord,
    SubtitleCandidateRecord,
)
from core.artifacts.registry import ArtifactRegistry

__all__ = [
    # Facade and ledger
    "ArtifactRegistry",
    "ProcessingLedger",
    # Record types
    "MediaAssetRecord",
    "StreamAssetRecord",
    "SubtitleCandidateRecord",
    "BenchmarkRunRecord",
    "BenchmarkComparisonRecord",
    "ArtifactRecord",
    "ReviewTaskRecord",
    "StateTransitionRecord",
    # Candidate status constants
    "CANDIDATE_STATUS_PENDING",
    "CANDIDATE_STATUS_ACCEPTED",
    "CANDIDATE_STATUS_FAILED",
    "CANDIDATE_STATUS_REVIEW_REQUIRED",
    "CANDIDATE_STATUSES",
    # Review status constants
    "REVIEW_STATUS_PENDING",
    "REVIEW_STATUS_APPROVED",
    "REVIEW_STATUS_REJECTED",
    "REVIEW_STATUS_REPROCESS",
    "REVIEW_STATUSES",
    # Artifact status constants
    "ARTIFACT_STATUS_ACTIVE",
    "ARTIFACT_STATUS_SUPERSEDED",
    "ARTIFACT_STATUS_DELETED",
    "ARTIFACT_STATUSES",
]
