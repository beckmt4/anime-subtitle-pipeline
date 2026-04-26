"""core.artifacts.schema -- SQLite schema definition and initialisation.

Creates and migrates the artifact registry database.  The schema is
forward-compatible: new columns are added with ALTER TABLE so existing
databases are upgraded automatically.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union

# ---------------------------------------------------------------------------
# DDL -- one statement per table, order matters due to FK references
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
    stream_type     TEXT    NOT NULL,
    language        TEXT,
    codec           TEXT,
    title           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_PIPELINE_RUNS = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    NOT NULL UNIQUE,
    media_hash      TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'running',
    config_json     TEXT    NOT NULL DEFAULT '{}',
    started_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    error_message   TEXT
);
"""

_CREATE_SUBTITLE_CANDIDATES = """
CREATE TABLE IF NOT EXISTS subtitle_candidates (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash          TEXT    NOT NULL,
    source_id           TEXT    NOT NULL,
    model_version       TEXT    NOT NULL DEFAULT '',
    language            TEXT    NOT NULL,
    source              TEXT    NOT NULL,
    origin_stream       TEXT    NOT NULL,
    parent_candidate_id INTEGER REFERENCES subtitle_candidates(id),
    segments_json       TEXT    NOT NULL DEFAULT '[]',
    meta_json           TEXT    NOT NULL DEFAULT '{}',
    status              TEXT    NOT NULL DEFAULT 'pending',
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
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
    reprocess_reason  TEXT,
    reviewer_notes    TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_ARTIFACTS = """
CREATE TABLE IF NOT EXISTS artifacts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash       TEXT    NOT NULL,
    artifact_type    TEXT    NOT NULL,
    file_path        TEXT    NOT NULL,
    candidate_id     INTEGER REFERENCES subtitle_candidates(id) ON DELETE SET NULL,
    pipeline_run_id  INTEGER REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    file_hash        TEXT,
    version          INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_media_assets_hash ON media_assets(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_stream_assets_media ON stream_assets(media_asset_id);",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_media ON pipeline_runs(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_media ON subtitle_candidates(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_source ON subtitle_candidates(source_id, model_version);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_status ON subtitle_candidates(status);",
    "CREATE INDEX IF NOT EXISTS idx_candidates_parent ON subtitle_candidates(parent_candidate_id);",
    "CREATE INDEX IF NOT EXISTS idx_benchmark_media ON benchmark_runs(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_review_tasks_candidate ON review_tasks(candidate_id);",
    "CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review_tasks(status);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_media ON artifacts(media_hash);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_candidate ON artifacts(candidate_id);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_pipeline_run ON artifacts(pipeline_run_id);",
    "CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type);",
]

_ALL_DDL = [
    _CREATE_MEDIA_ASSETS,
    _CREATE_STREAM_ASSETS,
    _CREATE_PIPELINE_RUNS,
    _CREATE_SUBTITLE_CANDIDATES,
    _CREATE_BENCHMARK_RUNS,
    _CREATE_REVIEW_TASKS,
    _CREATE_ARTIFACTS,
    *_INDEXES,
]

# ---------------------------------------------------------------------------
# Migrations -- applied once per database via a _schema_migrations table.
# Each entry is (description, SQL).
# ---------------------------------------------------------------------------

_MIGRATIONS = [
    (
        "add parent_candidate_id to subtitle_candidates",
        "ALTER TABLE subtitle_candidates ADD COLUMN "
        "parent_candidate_id INTEGER REFERENCES subtitle_candidates(id);",
    ),
]

_CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS _schema_migrations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT    NOT NULL UNIQUE,
    applied_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Run any pending schema migrations against conn."""
    conn.execute(_CREATE_MIGRATIONS_TABLE)
    for description, sql in _MIGRATIONS:
        already_run = conn.execute(
            "SELECT 1 FROM _schema_migrations WHERE description = ?", (description,)
        ).fetchone()
        if already_run:
            continue
        try:
            conn.execute(sql)
        except Exception:
            # Column may already exist in fresh DBs created from current DDL.
            pass
        conn.execute(
            "INSERT OR IGNORE INTO _schema_migrations (description) VALUES (?)",
            (description,),
        )


def init_db(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Open (or create) the artifact registry database and apply the schema.

    Args:
        db_path: Filesystem path to the SQLite file, or ':memory:' for tests.

    Returns:
        An open sqlite3.Connection with row_factory set to sqlite3.Row.
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
