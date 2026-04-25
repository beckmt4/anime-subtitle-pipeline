"""core.artifacts.registry — ArtifactRegistry: the main storage facade.

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
            segments=[{"start": 0.0, "end": 2.0, "text": "こんにちは"}],
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
    ARTIFACT_STATUSES,
    BenchmarkComparisonRecord,
    BenchmarkRunRecord,
    CANDIDATE_STATUSES,
    MediaAssetRecord,
    REVIEW_STATUSES,
    ReviewTaskRecord,
    StateTransitionRecord,
    StreamAssetRecord,
    SubtitleCandidateRecord,
)
from core.artifacts.schema import init_db


class ArtifactRegistry:
    """Facade for all reads and writes to the artifact SQLite database.

    Args:
        db_path: Path to the SQLite file, or ``":memory:"`` for tests.
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
        """Insert a new media asset or update its path/duration on hash collision.

        Returns the persisted :class:`~core.artifacts.models.MediaAssetRecord`
        with ``id`` and ``created_at`` populated.
        """
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO media_assets (media_hash, file_path, file_name, duration_sec)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(media_hash) DO UPDATE SET
                    file_path   = excluded.file_path,
                    file_name   = excluded.file_name,
                    duration_sec = excluded.duration_sec,
                    updated_at  = datetime('now')
                """,
                (media_hash, file_path, file_name, duration_sec),
            )
        row = self._conn.execute(
            "SELECT * FROM media_assets WHERE media_hash = ?", (media_hash,)
        ).fetchone()
        return _row_to_media_asset(row)

    def get_media_asset(self, media_hash: str) -> Optional[MediaAssetRecord]:
        """Return the :class:`MediaAssetRecord` for *media_hash*, or ``None``."""
        row = self._conn.execute(
            "SELECT * FROM media_assets WHERE media_hash = ?", (media_hash,)
        ).fetchone()
        return _row_to_media_asset(row) if row else None

    def list_media_assets(self) -> List[MediaAssetRecord]:
        """Return all stored media assets ordered by ``created_at`` ascending."""
        rows = self._conn.execute(
            "SELECT * FROM media_assets ORDER BY created_at ASC"
        ).fetchall()
        return [_row_to_media_asset(r) for r in rows]

    # ------------------------------------------------------------------
    # StreamAsset
    # ------------------------------------------------------------------

    def store_stream_asset(self, record: StreamAssetRecord) -> StreamAssetRecord:
        """Persist a stream asset; returns the record with ``id`` set."""
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
        """Persist a subtitle candidate; returns the record with ``id`` set.

        Raises:
            ValueError: If ``record.status`` is not one of :data:`CANDIDATE_STATUSES`.
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
                     origin_stream, parent_candidate_id, segments_json, meta_json, status)
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
        """Return the :class:`SubtitleCandidateRecord` with *candidate_id*, or ``None``."""
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
        """Return all candidates for *media_hash*, optionally filtered by *status*."""
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
            ValueError: If *status* is not one of :data:`CANDIDATE_STATUSES`.
            LookupError: If no candidate with *candidate_id* exists.
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
    # BenchmarkRun
    # ------------------------------------------------------------------

    def record_benchmark_run(self, record: BenchmarkRunRecord) -> BenchmarkRunRecord:
        """Persist a benchmark run; returns the record with ``id`` set.

        Raises:
            ValueError: If a run with the same ``run_id`` already exists.
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
        """Return the :class:`BenchmarkRunRecord` with *run_id*, or ``None``."""
        row = self._conn.execute(
            "SELECT * FROM benchmark_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return _row_to_benchmark_run(row) if row else None

    def list_benchmark_runs(self, media_hash: str) -> List[BenchmarkRunRecord]:
        """Return all benchmark runs for *media_hash* ordered by ``created_at``."""
        rows = self._conn.execute(
            "SELECT * FROM benchmark_runs WHERE media_hash = ? ORDER BY created_at ASC",
            (media_hash,),
        ).fetchall()
        return [_row_to_benchmark_run(r) for r in rows]

    # ------------------------------------------------------------------
    # ReviewTask
    # ------------------------------------------------------------------

    def create_review_task(self, record: ReviewTaskRecord) -> ReviewTaskRecord:
        """Persist a review task; returns the record with ``id`` set.

        Raises:
            ValueError: If ``record.status`` is not one of :data:`REVIEW_STATUSES`.
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
        """Return the :class:`ReviewTaskRecord` with *task_id*, or ``None``."""
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
            ValueError: If *status* is not one of :data:`REVIEW_STATUSES`.
            LookupError: If no task with *task_id* exists.
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
        """Return review tasks, optionally filtered by *media_hash* and/or *status*."""
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

    def add_review_task_candidate(self, task_id: int, candidate_id: int) -> None:
        """Associate an additional candidate with a review task.

        Uses the ``review_task_candidates`` join table so a single review task
        can cover multiple candidates.

        Raises:
            LookupError: If no task with *task_id* or candidate with
                         *candidate_id* exists.
        """
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO review_task_candidates"
                    " (review_task_id, candidate_id) VALUES (?, ?)",
                    (task_id, candidate_id),
                )
        except sqlite3.IntegrityError as exc:
            raise LookupError(
                f"review_task id={task_id} or candidate id={candidate_id} not found."
            ) from exc

    def get_review_task_candidate_ids(self, task_id: int) -> List[int]:
        """Return all candidate IDs associated with *task_id* via the join table."""
        rows = self._conn.execute(
            "SELECT candidate_id FROM review_task_candidates"
            " WHERE review_task_id = ? ORDER BY candidate_id ASC",
            (task_id,),
        ).fetchall()
        return [r["candidate_id"] for r in rows]

    # ------------------------------------------------------------------
    # BenchmarkComparison
    # ------------------------------------------------------------------

    def store_benchmark_comparison(
        self, record: BenchmarkComparisonRecord
    ) -> BenchmarkComparisonRecord:
        """Persist a benchmark comparison row; returns the record with ``id`` set."""
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO benchmark_comparisons
                    (benchmark_run_id, reference_candidate_id,
                     hypothesis_candidate_id, metric_name, metric_value, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.benchmark_run_id,
                    record.reference_candidate_id,
                    record.hypothesis_candidate_id,
                    record.metric_name,
                    record.metric_value,
                    json.dumps(record.meta, ensure_ascii=False),
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM benchmark_comparisons WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_benchmark_comparison(row)

    def list_benchmark_comparisons(
        self, benchmark_run_id: int
    ) -> List[BenchmarkComparisonRecord]:
        """Return all comparison rows for *benchmark_run_id*."""
        rows = self._conn.execute(
            "SELECT * FROM benchmark_comparisons WHERE benchmark_run_id = ?"
            " ORDER BY metric_name ASC",
            (benchmark_run_id,),
        ).fetchall()
        return [_row_to_benchmark_comparison(r) for r in rows]

    # ------------------------------------------------------------------
    # Artifact
    # ------------------------------------------------------------------

    def store_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        """Persist an artifact; returns the record with ``id`` set.

        Raises:
            ValueError: If ``record.status`` is not one of :data:`ARTIFACT_STATUSES`.
        """
        if record.status not in ARTIFACT_STATUSES:
            raise ValueError(
                f"Invalid artifact status {record.status!r}. "
                f"Must be one of {sorted(ARTIFACT_STATUSES)}."
            )
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO artifacts
                    (candidate_id, media_hash, artifact_type, file_path,
                     file_hash, version, status, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.candidate_id,
                    record.media_hash,
                    record.artifact_type,
                    record.file_path,
                    record.file_hash,
                    record.version,
                    record.status,
                    json.dumps(record.meta, ensure_ascii=False),
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM artifacts WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_artifact(row)

    def get_artifact(self, artifact_id: int) -> Optional[ArtifactRecord]:
        """Return the :class:`ArtifactRecord` with *artifact_id*, or ``None``."""
        row = self._conn.execute(
            "SELECT * FROM artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
        return _row_to_artifact(row) if row else None

    def list_artifacts(
        self,
        candidate_id: int,
        *,
        artifact_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[ArtifactRecord]:
        """Return artifacts for *candidate_id*, optionally filtered."""
        clauses: List[str] = ["candidate_id = ?"]
        params: List[object] = [candidate_id]
        if artifact_type is not None:
            clauses.append("artifact_type = ?")
            params.append(artifact_type)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(clauses)
        rows = self._conn.execute(
            f"SELECT * FROM artifacts {where} ORDER BY version ASC",
            params,
        ).fetchall()
        return [_row_to_artifact(r) for r in rows]

    def update_artifact_status(self, artifact_id: int, status: str) -> None:
        """Update the status of a stored artifact.

        Raises:
            ValueError: If *status* is not one of :data:`ARTIFACT_STATUSES`.
            LookupError: If no artifact with *artifact_id* exists.
        """
        if status not in ARTIFACT_STATUSES:
            raise ValueError(
                f"Invalid artifact status {status!r}. "
                f"Must be one of {sorted(ARTIFACT_STATUSES)}."
            )
        with self._conn:
            cur = self._conn.execute(
                "UPDATE artifacts SET status = ? WHERE id = ?",
                (status, artifact_id),
            )
        if cur.rowcount == 0:
            raise LookupError(f"No artifact with id={artifact_id}")

    # ------------------------------------------------------------------
    # StateTransition
    # ------------------------------------------------------------------

    def record_state_transition(
        self, record: StateTransitionRecord
    ) -> StateTransitionRecord:
        """Persist a state-transition event; returns the record with ``id`` set."""
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO state_transitions
                    (entity_type, entity_id, from_status, to_status,
                     reason, actor, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.entity_type,
                    record.entity_id,
                    record.from_status,
                    record.to_status,
                    record.reason,
                    record.actor,
                    json.dumps(record.meta, ensure_ascii=False),
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM state_transitions WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_state_transition(row)

    def list_state_transitions(
        self, entity_type: str, entity_id: int
    ) -> List[StateTransitionRecord]:
        """Return all state-transition events for an entity, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM state_transitions"
            " WHERE entity_type = ? AND entity_id = ?"
            " ORDER BY created_at ASC",
            (entity_type, entity_id),
        ).fetchall()
        return [_row_to_state_transition(r) for r in rows]

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
# Row → dataclass helpers
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


def _row_to_benchmark_comparison(row: sqlite3.Row) -> BenchmarkComparisonRecord:
    return BenchmarkComparisonRecord(
        id=row["id"],
        benchmark_run_id=row["benchmark_run_id"],
        reference_candidate_id=row["reference_candidate_id"],
        hypothesis_candidate_id=row["hypothesis_candidate_id"],
        metric_name=row["metric_name"],
        metric_value=row["metric_value"],
        meta=json.loads(row["meta_json"]),
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


def _row_to_artifact(row: sqlite3.Row) -> ArtifactRecord:
    return ArtifactRecord(
        id=row["id"],
        candidate_id=row["candidate_id"],
        media_hash=row["media_hash"],
        artifact_type=row["artifact_type"],
        file_path=row["file_path"],
        file_hash=row["file_hash"],
        version=row["version"],
        status=row["status"],
        meta=json.loads(row["meta_json"]),
        created_at=row["created_at"],
    )


def _row_to_state_transition(row: sqlite3.Row) -> StateTransitionRecord:
    return StateTransitionRecord(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        from_status=row["from_status"],
        to_status=row["to_status"],
        reason=row["reason"],
        actor=row["actor"],
        meta=json.loads(row["meta_json"]),
        created_at=row["created_at"],
    )


__all__ = ["ArtifactRegistry"]
