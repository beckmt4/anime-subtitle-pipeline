"""core.artifacts.models — plain-data record classes for the artifact registry.

Each class mirrors a database table row and is intentionally lightweight
(stdlib-only dataclasses with no ORM magic).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MediaAssetRecord:
    """One row of the ``media_assets`` table.

    Attributes:
        media_hash:    SHA-256 hex digest of the file content (natural key).
        file_path:     Absolute or relative path as stored.
        file_name:     Basename of the file.
        duration_sec:  Duration in seconds if known, else ``None``.
        id:            Auto-assigned surrogate key (``None`` before INSERT).
        created_at:    ISO-8601 timestamp string (set by the database).
        updated_at:    ISO-8601 timestamp string (set by the database).
    """
    media_hash: str
    file_path: str
    file_name: str
    duration_sec: Optional[float] = None
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class StreamAssetRecord:
    """One row of the ``stream_assets`` table.

    Attributes:
        media_asset_id: FK to :class:`MediaAssetRecord.id`.
        stream_index:   Zero-based stream index within the container.
        stream_type:    ``'audio'``, ``'subtitle'``, or ``'video'``.
        language:       ISO 639-1/BCP-47 language code, if known.
        codec:          Codec name (e.g. ``'aac'``, ``'ass'``).
        title:          Stream title metadata if present.
        id:             Auto-assigned surrogate key (``None`` before INSERT).
        created_at:     ISO-8601 timestamp string (set by the database).
    """
    media_asset_id: int
    stream_index: int
    stream_type: str
    language: Optional[str] = None
    codec: Optional[str] = None
    title: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None


# Allowed status values for subtitle candidates
CANDIDATE_STATUS_PENDING = "pending"
CANDIDATE_STATUS_ACCEPTED = "accepted"
CANDIDATE_STATUS_FAILED = "failed"
CANDIDATE_STATUS_REVIEW_REQUIRED = "review_required"
CANDIDATE_STATUSES = frozenset({
    CANDIDATE_STATUS_PENDING,
    CANDIDATE_STATUS_ACCEPTED,
    CANDIDATE_STATUS_FAILED,
    CANDIDATE_STATUS_REVIEW_REQUIRED,
})


@dataclass
class SubtitleCandidateRecord:
    """One row of the ``subtitle_candidates`` table.

    Attributes:
        media_hash:          SHA-256 hex digest of the source media file.
        source_id:           ``SubtitleCandidate.id`` (e.g. ``'asr_ja'``).
        model_version:       String identifying the model/version used.
        language:            ISO 639-1 language code.
        source:              Origin type: ``'asr'``, ``'embedded'``, ``'mt'``, ``'mt_llm'``.
        origin_stream:       Stream identifier (``'audio:1'``, ``'sub:0'``, filename).
        segments:            List of segment dicts (serialised to JSON in the DB).
        meta:                Additional metadata dict.
        status:              One of :data:`CANDIDATE_STATUSES`.
        parent_candidate_id: FK to the candidate this was derived from, or ``None``.
        id:                  Auto-assigned surrogate key (``None`` before INSERT).
        created_at:          ISO-8601 timestamp string (set by the database).
        updated_at:          ISO-8601 timestamp string (set by the database).
    """
    media_hash: str
    source_id: str
    language: str
    source: str
    origin_stream: str
    model_version: str = ""
    segments: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    status: str = CANDIDATE_STATUS_PENDING
    parent_candidate_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# Allowed status values for review tasks
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_REJECTED = "rejected"
REVIEW_STATUS_REPROCESS = "reprocess"
REVIEW_STATUSES = frozenset({
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_REJECTED,
    REVIEW_STATUS_REPROCESS,
})


@dataclass
class BenchmarkRunRecord:
    """One row of the ``benchmark_runs`` table.

    Attributes:
        media_hash:              SHA-256 hex digest of the source media file.
        run_id:                  Unique identifier for this benchmark run.
        metrics:                 Full metrics dict (WER, BLEU, chrF, …).
        reference_candidate_id:  FK to :class:`SubtitleCandidateRecord.id`, or ``None``.
        hypothesis_candidate_id: FK to :class:`SubtitleCandidateRecord.id`, or ``None``.
        wer:                     Word Error Rate snapshot (convenience column).
        bleu:                    BLEU score snapshot (convenience column).
        chrf:                    chrF score snapshot (convenience column).
        id:                      Auto-assigned surrogate key (``None`` before INSERT).
        created_at:              ISO-8601 timestamp string (set by the database).
    """
    media_hash: str
    run_id: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    reference_candidate_id: Optional[int] = None
    hypothesis_candidate_id: Optional[int] = None
    wer: Optional[float] = None
    bleu: Optional[float] = None
    chrf: Optional[float] = None
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class ReviewTaskRecord:
    """One row of the ``review_tasks`` table.

    Attributes:
        media_hash:       SHA-256 hex digest of the source media file.
        candidate_id:     FK to :class:`SubtitleCandidateRecord.id`.
        status:           One of :data:`REVIEW_STATUSES`.
        reprocess_reason: Free-text reason if status is ``'reprocess'``.
        reviewer_notes:   Free-text notes from the reviewer.
        id:               Auto-assigned surrogate key (``None`` before INSERT).
        created_at:       ISO-8601 timestamp string (set by the database).
        updated_at:       ISO-8601 timestamp string (set by the database).
    """
    media_hash: str
    candidate_id: int
    status: str = REVIEW_STATUS_PENDING
    reprocess_reason: Optional[str] = None
    reviewer_notes: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# Artifact type constants
ARTIFACT_TYPE_SRT = "srt"
ARTIFACT_TYPE_QC_JSON = "qc_json"
ARTIFACT_TYPE_MKV = "mkv"

# Allowed status values for pipeline runs
PIPELINE_STATUS_RUNNING = "running"
PIPELINE_STATUS_COMPLETED = "completed"
PIPELINE_STATUS_FAILED = "failed"


@dataclass
class PipelineRunRecord:
    """One row of the ``pipeline_runs`` table.

    Attributes:
        run_id:        Unique identifier for this pipeline run (UUID string).
        media_hash:    SHA-256 hex digest of the source media file.
        config:        Config snapshot dict (serialised to JSON in the DB).
        status:        One of ``'running'``, ``'completed'``, ``'failed'``.
        finished_at:   ISO-8601 timestamp when the run ended, or ``None``.
        error_message: Error description if status is ``'failed'``, else ``None``.
        id:            Auto-assigned surrogate key (``None`` before INSERT).
        created_at:    ISO-8601 timestamp string (set by the database).
    """
    run_id: str
    media_hash: str
    config: Dict[str, Any] = field(default_factory=dict)
    status: str = PIPELINE_STATUS_RUNNING
    finished_at: Optional[str] = None
    error_message: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class ArtifactRecord:
    """One row of the ``artifacts`` table.

    Attributes:
        media_hash:      SHA-256 hex digest of the source media file.
        artifact_type:   One of :data:`ARTIFACT_TYPE_SRT`, :data:`ARTIFACT_TYPE_QC_JSON`,
                         :data:`ARTIFACT_TYPE_MKV`.
        file_path:       Path to the output file as stored.
        candidate_id:    FK to :class:`SubtitleCandidateRecord.id`, or ``None``.
        pipeline_run_id: FK to :class:`PipelineRunRecord.id`, or ``None``.
        file_hash:       SHA-256 hex digest of the output file, or ``None``.
        id:              Auto-assigned surrogate key (``None`` before INSERT).
        created_at:      ISO-8601 timestamp string (set by the database).
    """
    media_hash: str
    artifact_type: str
    file_path: str
    candidate_id: Optional[int] = None
    pipeline_run_id: Optional[int] = None
    file_hash: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[str] = None


__all__ = [
    "MediaAssetRecord",
    "StreamAssetRecord",
    "SubtitleCandidateRecord",
    "BenchmarkRunRecord",
    "ReviewTaskRecord",
    "PipelineRunRecord",
    "ArtifactRecord",
    "CANDIDATE_STATUS_PENDING",
    "CANDIDATE_STATUS_ACCEPTED",
    "CANDIDATE_STATUS_FAILED",
    "CANDIDATE_STATUS_REVIEW_REQUIRED",
    "CANDIDATE_STATUSES",
    "REVIEW_STATUS_PENDING",
    "REVIEW_STATUS_APPROVED",
    "REVIEW_STATUS_REJECTED",
    "REVIEW_STATUS_REPROCESS",
    "REVIEW_STATUSES",
    "ARTIFACT_TYPE_SRT",
    "ARTIFACT_TYPE_QC_JSON",
    "ARTIFACT_TYPE_MKV",
    "PIPELINE_STATUS_RUNNING",
    "PIPELINE_STATUS_COMPLETED",
    "PIPELINE_STATUS_FAILED",
]
