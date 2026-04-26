"""core.artifacts -- processing ledger and artifact storage.

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
PipelineRunRecord             A single end-to-end pipeline invocation.
ArtifactRecord                An output file (SRT, MKV, QC JSON, benchmark JSON).
BenchmarkRunRecord            A benchmark run result snapshot.
ReviewTaskRecord              A review task (pending/approved/rejected/reprocess).

Status constants
----------------
CANDIDATE_STATUS_PENDING          'pending'
CANDIDATE_STATUS_ACCEPTED         'accepted'
CANDIDATE_STATUS_FAILED           'failed'
CANDIDATE_STATUS_REVIEW_REQUIRED  'review_required'
REVIEW_STATUS_PENDING             'pending'
REVIEW_STATUS_APPROVED            'approved'
REVIEW_STATUS_REJECTED            'rejected'
REVIEW_STATUS_REPROCESS           'reprocess'
PIPELINE_STATUS_RUNNING           'running'
PIPELINE_STATUS_COMPLETED         'completed'
PIPELINE_STATUS_FAILED            'failed'
PIPELINE_STATUS_CANCELLED         'cancelled'
ARTIFACT_TYPE_SRT                 'srt'
ARTIFACT_TYPE_MKV_BURNED          'mkv_burned'
ARTIFACT_TYPE_QC_JSON             'qc_json'
ARTIFACT_TYPE_BENCHMARK_JSON      'benchmark_json'
"""

from __future__ import annotations

from core.artifacts.ledger import ProcessingLedger
from core.artifacts.models import (
    ArtifactRecord,
    ARTIFACT_TYPE_BENCHMARK_JSON,
    ARTIFACT_TYPE_MKV_BURNED,
    ARTIFACT_TYPE_QC_JSON,
    ARTIFACT_TYPE_SRT,
    ARTIFACT_TYPES,
    BenchmarkRunRecord,
    CANDIDATE_STATUS_ACCEPTED,
    CANDIDATE_STATUS_FAILED,
    CANDIDATE_STATUS_PENDING,
    CANDIDATE_STATUS_REVIEW_REQUIRED,
    CANDIDATE_STATUSES,
    MediaAssetRecord,
    PIPELINE_STATUS_CANCELLED,
    PIPELINE_STATUS_COMPLETED,
    PIPELINE_STATUS_FAILED,
    PIPELINE_STATUS_RUNNING,
    PIPELINE_STATUSES,
    PipelineRunRecord,
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
    "PipelineRunRecord",
    "ArtifactRecord",
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
    # Pipeline run status constants
    "PIPELINE_STATUS_RUNNING",
    "PIPELINE_STATUS_COMPLETED",
    "PIPELINE_STATUS_FAILED",
    "PIPELINE_STATUS_CANCELLED",
    "PIPELINE_STATUSES",
    # Artifact type constants
    "ARTIFACT_TYPE_SRT",
    "ARTIFACT_TYPE_MKV_BURNED",
    "ARTIFACT_TYPE_QC_JSON",
    "ARTIFACT_TYPE_BENCHMARK_JSON",
    "ARTIFACT_TYPES",
]
