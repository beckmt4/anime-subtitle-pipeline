"""core.artifacts.schema — SQLite schema definition and initialisation.

Creates and migrates the artifact registry database.  The schema is intentionally
forward-compatible: new columns are added with ALTER TABLE so existing databases
are upgraded automatically.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union

# ---------------------------------------------------------------------------
# DDL — one statement per table, order matters due to FK references
# ---------------------------------------------------------------------------

_CREATE_MEDIA_ASSETS = """
CREATE TABLE IF NOT EXISTS media_assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash    TEXT    NOT NULL UNIQUE,
    file_path     TEXT    NOT NULL,
    file_name     TEXT    NOT NULL,
    duration_sec  REAL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_STREAM_ASSETS = """
CREATE TABLE IF NOT EXISTS stream_assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    media_asset_id  INTEGER NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    stream_index    INTEGER NOT NULL,
    stream_type     TEXT    NOT NULL,   -- 'audio' | 'subtitle' | 'video'
    language        TEXT,
    codec           TEXT,
    title           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_SUBTITLE_CANDIDATES = """
CREATE TABLE IF NOT EXISTS subtitle_candidates (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash           TEXT    NOT NULL,
    source_id            TEXT    NOT NULL,   -- SubtitleCandidate.id  e.g. 'asr_ja'
    model_version        TEXT    NOT NULL DEFAULT '',
    language             TEXT    NOT NULL,
    source               TEXT    NOT NULL,   -- 'asr' | 'embedded' | 'mt' | 'mt_llm'
    origin_stream        TEXT    NOT NULL,
    parent_candidate_id  INTEGER REFERENCES subtitle_candidates(id),
        -- NULL for source candidates; set for MT/LLM-derived candidates to trace lineage
    segments_json        TEXT    NOT NULL DEFAULT '[]',
    meta_json            TEXT    NOT NULL DEFAULT '{}',
    status               TEXT    NOT NULL DEFAULT 'pending',
        -- 'pending' | 'accepted' | 'failed' | 'review_required'
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_BENCHMARK_RUNS = """
CREATE TABLE IF NOT EXISTS benchmark_runs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash              TEXT    NOT NULL,
    run_id                  TEXT    NOT NULL UNIQUE,
    reference_candidate_id  INTEGER REFERENCES subtitle_candidates(id),
    hypothesis_candidate_id INTEGER REFERENCES subtitle_candidates(id),
    wer                     REAL,
    bleu                    REAL,
    chrf                    REAL,
    metrics_json            TEXT    NOT NULL DEFAULT '{}',
    created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_BENCHMARK_COMPARISONS = """
CREATE TABLE IF NOT EXISTS benchmark_comparisons (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_run_id        INTEGER NOT NULL REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    reference_candidate_id  INTEGER NOT NULL REFERENCES subtitle_candidates(id),
    hypothesis_candidate_id INTEGER NOT NULL REFERENCES subtitle_candidates(id),
    metric_name             TEXT    NOT NULL,   -- e.g. 'wer', 'bleu', 'chrf'
    metric_value            REAL    NOT NULL,
    meta_json               TEXT    NOT NULL DEFAULT '{}',
    created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_REVIEW_TASKS = """
CREATE TABLE IF NOT EXISTS review_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash        TEXT    NOT NULL,
    candidate_id      INTEGER NOT NULL REFERENCES subtitle_candidates(id) ON DELETE CASCADE,
        -- primary candidate under review; see review_task_candidates for multi-candidate tasks
    status            TEXT    NOT NULL DEFAULT 'pending',
        -- 'pending' | 'approved' | 'rejected' | 'reprocess'
    reprocess_reason  TEXT,
    reviewer_notes    TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_REVIEW_TASK_CANDIDATES = """
CREATE TABLE IF NOT EXISTS review_task_candidates (
    review_task_id  INTEGER NOT NULL REFERENCES review_tasks(id) ON DELETE CASCADE,
    candidate_id    INTEGER NOT NULL REFERENCES subtitle_candidates(id) ON DELETE CASCADE,
    PRIMARY KEY (review_task_id, candidate_id)
);
"""

_CREATE_ARTIFACTS = """
CREATE TABLE IF NOT EXISTS artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id    INTEGER NOT NULL REFERENCES subtitle_candidates(id) ON DELETE CASCADE,
    media_hash      TEXT    NOT NULL,
    artifact_type   TEXT    NOT NULL,   -- 'srt' | 'ass' | 'vtt' | 'json' | 'raw'
    file_path       TEXT    NOT NULL,
    file_hash       TEXT    NOT NULL,   -- SHA-256 of the artifact file content
    version         INTEGER NOT NULL DEFAULT 1,
        -- increments on reprocess; allows multiple versions of the same artifact type
    status          TEXT    NOT NULL DEFAULT 'active',
        -- 'active' | 'superseded' | 'deleted'
    meta_json       TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_STATE_TRANSITIONS = """
CREATE TABLE IF NOT EXISTS state_transitions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type  TEXT    NOT NULL,   -- 'subtitle_candidate' | 'review_task' | 'artifact'
    entity_id    INTEGER NOT NULL,
    from_status  TEXT,               -- NULL for the initial creation transition
    to_status    TEXT    NOT NULL,
    reason       TEXT,               -- free-text reason for the transition (e.g. reprocess reason)
    actor        TEXT,               -- system component or user that triggered the transition
    meta_json    TEXT    NOT NULL DEFAULT '{}',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

# Performance indexes
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_media_assets_hash ON media_assets(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_stream_assets_media ON stream_assets(media_asset_id);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_media ON subtitle_candidates(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_parent ON subtitle_candidates(parent_candidate_id);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_source ON subtitle_candidates(source_id, model_version);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_status ON subtitle_candidates(status);",
    "CREATE INDEX IF NOT EXISTS idx_benchmark_media ON benchmark_runs(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_benchmark_comparisons_run ON benchmark_comparisons(benchmark_run_id);",
    "CREATE INDEX IF NOT EXISTS idx_benchmark_comparisons_ref ON benchmark_comparisons(reference_candidate_id);",
    "CREATE INDEX IF NOT EXISTS idx_benchmark_comparisons_hyp ON benchmark_comparisons(hypothesis_candidate_id);",
    "CREATE INDEX IF NOT EXISTS idx_review_tasks_candidate ON review_tasks(candidate_id);",
    "CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review_tasks(status);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_candidate ON artifacts(candidate_id);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_media ON artifacts(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_status ON artifacts(status);",
    "CREATE INDEX IF NOT EXISTS idx_state_transitions_entity ON state_transitions(entity_type, entity_id);",
    "CREATE INDEX IF NOT EXISTS idx_state_transitions_created ON state_transitions(created_at);",
]

_ALL_DDL = [
    _CREATE_MEDIA_ASSETS,
    _CREATE_STREAM_ASSETS,
    _CREATE_SUBTITLE_CANDIDATES,
    _CREATE_BENCHMARK_RUNS,
    _CREATE_BENCHMARK_COMPARISONS,
    _CREATE_REVIEW_TASKS,
    _CREATE_REVIEW_TASK_CANDIDATES,
    _CREATE_ARTIFACTS,
    _CREATE_STATE_TRANSITIONS,
    *_INDEXES,
]

# ---------------------------------------------------------------------------
# Forward-compatibility migrations (ALTER TABLE for new columns)
# Applied in order; errors are silently ignored so they are idempotent.
# ---------------------------------------------------------------------------

_MIGRATIONS = [
    # v1: candidate lineage — add parent_candidate_id to pre-existing databases
    "ALTER TABLE subtitle_candidates ADD COLUMN parent_candidate_id INTEGER REFERENCES subtitle_candidates(id);",
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply forward-compatibility migrations idempotently."""
    for migration in _MIGRATIONS:
        try:
            with conn:
                conn.execute(migration)
        except sqlite3.OperationalError:
            pass  # column/object already exists — migration already applied


def init_db(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Open (or create) the artifact registry database and apply the schema.

    Args:
        db_path: Filesystem path to the SQLite file, or ``":memory:"`` for an
                 in-memory database (useful for tests).

    Returns:
        An open :class:`sqlite3.Connection` with ``row_factory`` set to
        :class:`sqlite3.Row` so columns can be accessed by name.
    """
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    with conn:
        for ddl in _ALL_DDL:
            conn.execute(ddl)
    _apply_migrations(conn)
    return conn
