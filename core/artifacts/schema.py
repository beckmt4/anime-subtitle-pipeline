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
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash      TEXT    NOT NULL,
    source_id       TEXT    NOT NULL,   -- SubtitleCandidate.id  e.g. 'asr_ja'
    model_version   TEXT    NOT NULL DEFAULT '',
    language        TEXT    NOT NULL,
    source          TEXT    NOT NULL,   -- 'asr' | 'embedded' | 'mt' | 'mt_llm'
    origin_stream   TEXT    NOT NULL,
    segments_json   TEXT    NOT NULL DEFAULT '[]',
    meta_json       TEXT    NOT NULL DEFAULT '{}',
    status          TEXT    NOT NULL DEFAULT 'pending',
        -- 'pending' | 'accepted' | 'failed' | 'review_required'
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
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

_CREATE_REVIEW_TASKS = """
CREATE TABLE IF NOT EXISTS review_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash        TEXT    NOT NULL,
    candidate_id      INTEGER NOT NULL REFERENCES subtitle_candidates(id) ON DELETE CASCADE,
    status            TEXT    NOT NULL DEFAULT 'pending',
        -- 'pending' | 'approved' | 'rejected' | 'reprocess'
    reprocess_reason  TEXT,
    reviewer_notes    TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_PIPELINE_RUNS = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT    NOT NULL UNIQUE,
    media_hash    TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'running',
        -- 'running' | 'completed' | 'failed'
    config_json   TEXT    NOT NULL DEFAULT '{}',
    finished_at   TEXT,
    error_message TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_ARTIFACTS = """
CREATE TABLE IF NOT EXISTS artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash      TEXT    NOT NULL,
    artifact_type   TEXT    NOT NULL,
    file_path       TEXT    NOT NULL,
    candidate_id    INTEGER REFERENCES subtitle_candidates(id),
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id),
    file_hash       TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

# Performance indexes
_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_media_assets_hash ON media_assets(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_stream_assets_media ON stream_assets(media_asset_id);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_media ON subtitle_candidates(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_source ON subtitle_candidates(source_id, model_version);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_status ON subtitle_candidates(status);",
    "CREATE INDEX IF NOT EXISTS idx_benchmark_media ON benchmark_runs(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_review_tasks_candidate ON review_tasks(candidate_id);",
    "CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review_tasks(status);",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_media ON pipeline_runs(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_media ON artifacts(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_candidate ON artifacts(candidate_id);",
]

# Migrations applied to existing databases (ALTER TABLE … ADD COLUMN IF NOT EXISTS
# is not supported in SQLite < 3.37, so we use a try/except approach).
_MIGRATIONS = [
    "ALTER TABLE subtitle_candidates ADD COLUMN parent_candidate_id INTEGER REFERENCES subtitle_candidates(id);",
]

_ALL_DDL = [
    _CREATE_MEDIA_ASSETS,
    _CREATE_STREAM_ASSETS,
    _CREATE_SUBTITLE_CANDIDATES,
    _CREATE_BENCHMARK_RUNS,
    _CREATE_REVIEW_TASKS,
    _CREATE_PIPELINE_RUNS,
    _CREATE_ARTIFACTS,
    *_INDEXES,
]


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
        # Apply forward-compatible migrations (ignore if column already exists).
        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
    return conn
