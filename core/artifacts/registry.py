"""core.artifacts.registry -- ArtifactRegistry: the main storage facade.

All writes and reads to the artifact database go through this class.  It
handles serialisation/deserialisation of JSON blobs and exposes a clean
Python API so callers never need to write raw SQL.

Typical usage::

    from core.artifacts import ArtifactRegistry
    from core.artifacts.models import SubtitleCandidateRecord

    registry = ArtifactRegistry(db_path="artifacts.db")

    # Store a media file
    asset = registry.upsert_media_asset(
        media_hash="abc123", file_path="/data/ep01.mkv", file_name="ep01.mkv"
    )

    # Store a subtitle candidate
    candidate = registry.store_candidate(
        SubtitleCandidateRecord(
            media_hash="abc123",
            source_id="asr_ja",
            language="ja",
            source="asr",
            origin_stream="audio:0",
            model_version="large-v3",
            segments=[{"start": 0.0, "end": 2.0, "text": "hello"}],
        )
    )

    # Update status
    registry.update_candidate_status(candidate.id, "accepted")
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Union

from core.artifacts.models import (
    ArtifactRecord,
    ARTIFACT_TYPES,
    BenchmarkRunRecord,
    CANDIDATE_STATUSES,
    MediaAssetRecord,
    PIPELINE_STATUSES,
    PipelineRunRecord,
    REVIEW_STATUSES,
    ReviewTaskRecord,
    StreamAssetRecord,
    SubtitleCandidateRecord,
)
from core.artifacts.schema import init_db


class ArtifactRegistry:
    """Facade for all reads and writes to the artifact SQLite database.

    Args:
        db_path: Path to the SQLite file, or ":memory:" for tests.
    """

    def __init__(self, db_path: Union[str, Path] = ":memory:") -> None:
        self._conn: sqlite3.Connection = init_db(db_path)

    # ------------------------------------------------------------------
    # MediaAsset
    # ------------------------------------------------------------------

    def upsert_media_asset(
        self,
        *,
        media_hash: str,
        file_path: str,
        file_name: str,
        duration_sec: Optional[float] = None,
    ) -> MediaAssetRecord:
        """Insert a new media asset or update its path/duration on hash collision."""
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO media_assets (media_hash, file_path, file_name, duration_sec)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(media_hash) DO UPDATE SET
                    file_path    = excluded.file_path,
                    file_name    = excluded.file_name,
                    duration_sec = excluded.duration_sec,
                    updated_at   = datetime('now')
                """,
                (media_hash, file_path, file_name, duration_sec),
            )
        row = self._conn.execute(
            "SELECT * FROM media_assets WHERE media_hash = ?", (media_hash,)
        ).fetchone()
        return _row_to_media_asset(row)

    def get_media_asset(self, media_hash: str) -> Optional[MediaAssetRecord]:
        """Return the MediaAssetRecord for media_hash, or None."""
        row = self._conn.execute(
            "SELECT * FROM media_assets WHERE media_hash = ?", (media_hash,)
        ).fetchone()
        return _row_to_media_asset(row) if row else None

    def list_media_assets(self) -> List[MediaAssetRecord]:
        """Return all stored media assets ordered by created_at ascending."""
        rows = self._conn.execute(
            "SELECT * FROM media_assets ORDER BY created_at ASC"
        ).fetchall()
        return [_row_to_media_asset(r) for r in rows]

    # ------------------------------------------------------------------
    # StreamAsset
    # ------------------------------------------------------------------

    def store_stream_asset(self, record: StreamAssetRecord) -> StreamAssetRecord:
        """Persist a stream asset; returns the record with id set."""
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO stream_assets
                    (media_asset_id, stream_index, stream_type, language, codec, title)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.media_asset_id,
                    record.stream_index,
                    record.stream_type,
                    record.language,
                    record.codec,
                    record.title,
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM stream_assets WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_stream_asset(row)

    def list_stream_assets(self, media_asset_id: int) -> List[StreamAssetRecord]:
        """Return all stream assets for a given media asset."""
        rows = self._conn.execute(
            "SELECT * FROM stream_assets WHERE media_asset_id = ? ORDER BY stream_index ASC",
            (media_asset_id,),
        ).fetchall()
        return [_row_to_stream_asset(r) for r in rows]

    # ------------------------------------------------------------------
    # SubtitleCandidate
    # ------------------------------------------------------------------

    def store_candidate(self, record: SubtitleCandidateRecord) -> SubtitleCandidateRecord:
        """Persist a subtitle candidate; returns the record with id set.

        Raises:
            ValueError: If record.status is not one of CANDIDATE_STATUSES.
        """
        if record.status not in CANDIDATE_STATUSES:
            raise ValueError(
                f"Invalid candidate status {record.status!r}. "
                f"Must be one of {sorted(CANDIDATE_STATUSES)}."
            )
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO subtitle_candidates
                    (media_hash, source_id, model_version, language, source,
                     origin_stream, parent_candidate_id,
                     segments_json, meta_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.media_hash,
                    record.source_id,
                    record.model_version,
                    record.language,
                    record.source,
                    record.origin_stream,
                    record.parent_candidate_id,
                    json.dumps(record.segments, ensure_ascii=False),
                    json.dumps(record.meta, ensure_ascii=False),
                    record.status,
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM subtitle_candidates WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_candidate(row)

    def get_candidate(self, candidate_id: int) -> Optional[SubtitleCandidateRecord]:
        """Return the SubtitleCandidateRecord with candidate_id, or None."""
        row = self._conn.execute(
            "SELECT * FROM subtitle_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        return _row_to_candidate(row) if row else None

    def list_candidates(
        self,
        media_hash: str,
        *,
        status: Optional[str] = None,
    ) -> List[SubtitleCandidateRecord]:
        """Return all candidates for media_hash, optionally filtered by status."""
        if status is not None:
            rows = self._conn.execute(
                "SELECT * FROM subtitle_candidates WHERE media_hash = ? AND status = ?"
                " ORDER BY created_at ASC",
                (media_hash, status),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM subtitle_candidates WHERE media_hash = ?"
                " ORDER BY created_at ASC",
                (media_hash,),
            ).fetchall()
        return [_row_to_candidate(r) for r in rows]

    def update_candidate_status(self, candidate_id: int, status: str) -> None:
        """Update the status of a stored candidate.

        Raises:
            ValueError: If status is not one of CANDIDATE_STATUSES.
            LookupError: If no candidate with candidate_id exists.
        """
        if status not in CANDIDATE_STATUSES:
            raise ValueError(
                f"Invalid candidate status {status!r}. "
                f"Must be one of {sorted(CANDIDATE_STATUSES)}."
            )
        with self._conn:
            cur = self._conn.execute(
                "UPDATE subtitle_candidates SET status = ?, updated_at = datetime('now')"
                " WHERE id = ?",
                (status, candidate_id),
            )
        if cur.rowcount == 0:
            raise LookupError(f"No subtitle candidate with id={candidate_id}")

    # ------------------------------------------------------------------
    # PipelineRun
    # ------------------------------------------------------------------

    def create_pipeline_run(self, record: PipelineRunRecord) -> PipelineRunRecord:
        """Persist a new pipeline run; returns the record with id and started_at set.

        Raises:
            ValueError: If record.status is invalid or run_id already exists.
        """
        if record.status not in PIPELINE_STATUSES:
            raise ValueError(
                f"Invalid pipeline status {record.status!r}. "
                f"Must be one of {sorted(PIPELINE_STATUSES)}."
            )
        try:
            with self._conn:
                cur = self._conn.execute(
                    """
                    INSERT INTO pipeline_runs
                        (run_id, media_hash, status, config_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        record.run_id,
                        record.media_hash,
                        record.status,
                        json.dumps(record.config, ensure_ascii=False),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"A pipeline run with run_id={record.run_id!r} already exists."
            ) from exc
        row = self._conn.execute(
            "SELECT * FROM pipeline_runs WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_pipeline_run(row)

    def get_pipeline_run(self, run_id: str) -> Optional[PipelineRunRecord]:
        """Return the PipelineRunRecord with run_id, or None."""
        row = self._conn.execute(
            "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return _row_to_pipeline_run(row) if row else None

    def list_pipeline_runs(
        self,
        media_hash: str,
        *,
        status: Optional[str] = None,
    ) -> List[PipelineRunRecord]:
        """Return all pipeline runs for media_hash, optionally filtered by status."""
        if status is not None:
            rows = self._conn.execute(
                "SELECT * FROM pipeline_runs WHERE media_hash = ? AND status = ?"
                " ORDER BY started_at ASC",
                (media_hash, status),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM pipeline_runs WHERE media_hash = ?"
                " ORDER BY started_at ASC",
                (media_hash,),
            ).fetchall()
        return [_row_to_pipeline_run(r) for r in rows]

    def finish_pipeline_run(
        self,
        run_id: str,
        *,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Mark a pipeline run as finished.

        Sets finished_at to the current UTC time and updates status and
        optionally error_message.

        Raises:
            ValueError: If status is not one of PIPELINE_STATUSES.
            LookupError: If no run with run_id exists.
        """
        if status not in PIPELINE_STATUSES:
            raise ValueError(
                f"Invalid pipeline status {status!r}. "
                f"Must be one of {sorted(PIPELINE_STATUSES)}."
            )
        with self._conn:
            cur = self._conn.execute(
                """
                UPDATE pipeline_runs
                SET status = ?, error_message = ?, finished_at = datetime('now')
                WHERE run_id = ?
                """,
                (status, error_message, run_id),
            )
        if cur.rowcount == 0:
            raise LookupError(f"No pipeline run with run_id={run_id!r}")

    # ------------------------------------------------------------------
    # Artifact
    # ------------------------------------------------------------------

    def store_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        """Persist an output artifact; returns the record with id set.

        Raises:
            ValueError: If record.artifact_type is not one of ARTIFACT_TYPES.
        """
        if record.artifact_type not in ARTIFACT_TYPES:
            raise ValueError(
                f"Invalid artifact_type {record.artifact_type!r}. "
                f"Must be one of {sorted(ARTIFACT_TYPES)}."
            )
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO artifacts
                    (media_hash, artifact_type, file_path,
                     candidate_id, pipeline_run_id, file_hash, version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.media_hash,
                    record.artifact_type,
                    record.file_path,
                    record.candidate_id,
                    record.pipeline_run_id,
                    record.file_hash,
                    record.version,
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM artifacts WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_artifact(row)

    def get_artifact(self, artifact_id: int) -> Optional[ArtifactRecord]:
        """Return the ArtifactRecord with artifact_id, or None."""
        row = self._conn.execute(
            "SELECT * FROM artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
        return _row_to_artifact(row) if row else None

    def list_artifacts(
        self,
        media_hash: str,
        *,
        artifact_type: Optional[str] = None,
        candidate_id: Optional[int] = None,
    ) -> List[ArtifactRecord]:
        """Return artifacts for media_hash, optionally filtered by type or candidate."""
        clauses = ["media_hash = ?"]
        params: list = [media_hash]
        if artifact_type is not None:
            clauses.append("artifact_type = ?")
            params.append(artifact_type)
        if candidate_id is not None:
            clauses.append("candidate_id = ?")
            params.append(candidate_id)
        where = " AND ".join(clauses)
        rows = self._conn.execute(
            f"SELECT * FROM artifacts WHERE {where} ORDER BY created_at ASC",
            params,
        ).fetchall()
        return [_row_to_artifact(r) for r in rows]

    # ------------------------------------------------------------------
    # BenchmarkRun
    # ------------------------------------------------------------------

    def record_benchmark_run(self, record: BenchmarkRunRecord) -> BenchmarkRunRecord:
        """Persist a benchmark run; returns the record with id set.

        Raises:
            ValueError: If a run with the same run_id already exists.
        """
        wer = record.wer if record.wer is not None else record.metrics.get("wer")
        bleu = record.bleu if record.bleu is not None else record.metrics.get("bleu")
        chrf = record.chrf if record.chrf is not None else record.metrics.get("chrf")
        try:
            with self._conn:
                cur = self._conn.execute(
                    """
                    INSERT INTO benchmark_runs
                        (media_hash, run_id, reference_candidate_id,
                         hypothesis_candidate_id, wer, bleu, chrf, metrics_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.media_hash,
                        record.run_id,
                        record.reference_candidate_id,
                        record.hypothesis_candidate_id,
                        wer,
                        bleu,
                        chrf,
                        json.dumps(record.metrics, ensure_ascii=False),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"A benchmark run with run_id={record.run_id!r} already exists."
            ) from exc
        row = self._conn.execute(
            "SELECT * FROM benchmark_runs WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_benchmark_run(row)

    def get_benchmark_run(self, run_id: str) -> Optional[BenchmarkRunRecord]:
        """Return the BenchmarkRunRecord with run_id, or None."""
        row = self._conn.execute(
            "SELECT * FROM benchmark_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return _row_to_benchmark_run(row) if row else None

    def list_benchmark_runs(self, media_hash: str) -> List[BenchmarkRunRecord]:
        """Return all benchmark runs for media_hash ordered by created_at."""
        rows = self._conn.execute(
            "SELECT * FROM benchmark_runs WHERE media_hash = ? ORDER BY created_at ASC",
            (media_hash,),
        ).fetchall()
        return [_row_to_benchmark_run(r) for r in rows]

    # ------------------------------------------------------------------
    # ReviewTask
    # ------------------------------------------------------------------

    def create_review_task(self, record: ReviewTaskRecord) -> ReviewTaskRecord:
        """Persist a review task; returns the record with id set.

        Raises:
            ValueError: If record.status is not one of REVIEW_STATUSES.
        """
        if record.status not in REVIEW_STATUSES:
            raise ValueError(
                f"Invalid review status {record.status!r}. "
                f"Must be one of {sorted(REVIEW_STATUSES)}."
            )
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO review_tasks
                    (media_hash, candidate_id, status, reprocess_reason, reviewer_notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.media_hash,
                    record.candidate_id,
                    record.status,
                    record.reprocess_reason,
                    record.reviewer_notes,
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM review_tasks WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_review_task(row)

    def get_review_task(self, task_id: int) -> Optional[ReviewTaskRecord]:
        """Return the ReviewTaskRecord with task_id, or None."""
        row = self._conn.execute(
            "SELECT * FROM review_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return _row_to_review_task(row) if row else None

    def update_review_task(
        self,
        task_id: int,
        *,
        status: str,
        reprocess_reason: Optional[str] = None,
        reviewer_notes: Optional[str] = None,
    ) -> None:
        """Update the status (and optional notes) of a review task.

        Raises:
            ValueError: If status is not one of REVIEW_STATUSES.
            LookupError: If no task with task_id exists.
        """
        if status not in REVIEW_STATUSES:
            raise ValueError(
                f"Invalid review status {status!r}. "
                f"Must be one of {sorted(REVIEW_STATUSES)}."
            )
        with self._conn:
            cur = self._conn.execute(
                """
                UPDATE review_tasks
                SET status = ?, reprocess_reason = ?, reviewer_notes = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (status, reprocess_reason, reviewer_notes, task_id),
            )
        if cur.rowcount == 0:
            raise LookupError(f"No review task with id={task_id}")

    def list_review_tasks(
        self,
        media_hash: Optional[str] = None,
        *,
        status: Optional[str] = None,
    ) -> List[ReviewTaskRecord]:
        """Return review tasks, optionally filtered by media_hash and/or status."""
        clauses, params = [], []
        if media_hash is not None:
            clauses.append("media_hash = ?")
            params.append(media_hash)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM review_tasks {where} ORDER BY created_at ASC",
            params,
        ).fetchall()
        return [_row_to_review_task(r) for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self) -> "ArtifactRegistry":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Row -> dataclass helpers
# ---------------------------------------------------------------------------

def _row_to_media_asset(row: sqlite3.Row) -> MediaAssetRecord:
    return MediaAssetRecord(
        id=row["id"],
        media_hash=row["media_hash"],
        file_path=row["file_path"],
        file_name=row["file_name"],
        duration_sec=row["duration_sec"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_stream_asset(row: sqlite3.Row) -> StreamAssetRecord:
    return StreamAssetRecord(
        id=row["id"],
        media_asset_id=row["media_asset_id"],
        stream_index=row["stream_index"],
        stream_type=row["stream_type"],
        language=row["language"],
        codec=row["codec"],
        title=row["title"],
        created_at=row["created_at"],
    )


def _row_to_candidate(row: sqlite3.Row) -> SubtitleCandidateRecord:
    return SubtitleCandidateRecord(
        id=row["id"],
        media_hash=row["media_hash"],
        source_id=row["source_id"],
        model_version=row["model_version"],
        language=row["language"],
        source=row["source"],
        origin_stream=row["origin_stream"],
        parent_candidate_id=row["parent_candidate_id"],
        segments=json.loads(row["segments_json"]),
        meta=json.loads(row["meta_json"]),
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_pipeline_run(row: sqlite3.Row) -> PipelineRunRecord:
    return PipelineRunRecord(
        id=row["id"],
        run_id=row["run_id"],
        media_hash=row["media_hash"],
        status=row["status"],
        config=json.loads(row["config_json"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error_message=row["error_message"],
    )


def _row_to_artifact(row: sqlite3.Row) -> ArtifactRecord:
    return ArtifactRecord(
        id=row["id"],
        media_hash=row["media_hash"],
        artifact_type=row["artifact_type"],
        file_path=row["file_path"],
        candidate_id=row["candidate_id"],
        pipeline_run_id=row["pipeline_run_id"],
        file_hash=row["file_hash"],
        version=row["version"],
        created_at=row["created_at"],
    )


def _row_to_benchmark_run(row: sqlite3.Row) -> BenchmarkRunRecord:
    return BenchmarkRunRecord(
        id=row["id"],
        media_hash=row["media_hash"],
        run_id=row["run_id"],
        reference_candidate_id=row["reference_candidate_id"],
        hypothesis_candidate_id=row["hypothesis_candidate_id"],
        wer=row["wer"],
        bleu=row["bleu"],
        chrf=row["chrf"],
        metrics=json.loads(row["metrics_json"]),
        created_at=row["created_at"],
    )


def _row_to_review_task(row: sqlite3.Row) -> ReviewTaskRecord:
    return ReviewTaskRecord(
        id=row["id"],
        media_hash=row["media_hash"],
        candidate_id=row["candidate_id"],
        status=row["status"],
        reprocess_reason=row["reprocess_reason"],
        reviewer_notes=row["reviewer_notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


__all__ = ["ArtifactRegistry"]
