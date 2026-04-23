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
ReviewTaskRecord              A review task (pending/approved/rejected/reprocess).

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
"""

from __future__ import annotations

from core.artifacts.ledger import ProcessingLedger
from core.artifacts.models import (
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
    "ReviewTaskRecord",
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
]
