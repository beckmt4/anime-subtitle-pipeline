"""core.artifacts.schema — SQLite schema definition and initialisation.

Creates and migrates the artifact registry database.  The schema is intentionally
forward-compatible: new columns are added with ALTER TABLE so existing databases
are upgraded automatically.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Iterable, Optional, Union

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
    history_json      TEXT    NOT NULL DEFAULT '[]',
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

_CREATE_SCHEMA_MIGRATIONS = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT    NOT NULL UNIQUE,
    checksum_sha256 TEXT    NOT NULL,
    applied_at      TEXT    NOT NULL DEFAULT (datetime('now'))
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
    "ALTER TABLE review_tasks ADD COLUMN history_json TEXT NOT NULL DEFAULT '[]';",
]

_ALL_DDL = [
    _CREATE_MEDIA_ASSETS,
    _CREATE_STREAM_ASSETS,
    _CREATE_SUBTITLE_CANDIDATES,
    _CREATE_BENCHMARK_RUNS,
    _CREATE_REVIEW_TASKS,
    _CREATE_PIPELINE_RUNS,
    _CREATE_ARTIFACTS,
    _CREATE_SCHEMA_MIGRATIONS,
    *_INDEXES,
]


def _default_migrations_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "migrations"


def _iter_sql_statements(script: str) -> Iterable[str]:
    statement = ""
    for line in script.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            stripped = statement.strip()
            if stripped:
                yield stripped
            statement = ""
    if statement.strip():
        yield statement.strip()


def _apply_sql_migrations(
    conn: sqlite3.Connection,
    migrations_dir: Union[str, Path],
) -> None:
    """Apply unapplied numbered SQL files from *migrations_dir*.

    Migration identity is the filename. If an already-applied filename changes
    contents, startup fails instead of silently running an edited migration.
    """
    path = Path(migrations_dir)
    if not path.exists():
        return
    if not path.is_dir():
        raise ValueError(f"Migration path is not a directory: {path}")

    migration_files = sorted(p for p in path.glob("*.sql") if p.is_file())
    for migration_file in migration_files:
        sql = migration_file.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        row = conn.execute(
            "SELECT checksum_sha256 FROM schema_migrations WHERE filename = ?",
            (migration_file.name,),
        ).fetchone()
        if row is not None:
            if row["checksum_sha256"] != checksum:
                raise ValueError(
                    f"Applied migration {migration_file.name!r} has changed checksum"
                )
            continue

        with conn:
            for statement in _iter_sql_statements(sql):
                conn.execute(statement)
            conn.execute(
                """
                INSERT INTO schema_migrations (filename, checksum_sha256)
                VALUES (?, ?)
                """,
                (migration_file.name, checksum),
            )


def init_db(
    db_path: Union[str, Path],
    *,
    migrations_dir: Optional[Union[str, Path]] = None,
) -> sqlite3.Connection:
    """Open (or create) the artifact registry database and apply the schema.

    Args:
        db_path: Filesystem path to the SQLite file, or ``":memory:"`` for an
                 in-memory database (useful for tests).
        migrations_dir: Optional directory of numbered ``*.sql`` migrations.
                        Defaults to ``docs/migrations`` when present.

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
    _apply_sql_migrations(conn, migrations_dir or _default_migrations_dir())
    return conn
