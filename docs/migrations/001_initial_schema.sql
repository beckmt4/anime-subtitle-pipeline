-- Migration 001 — initial schema
-- Applied by: core/artifacts/schema.py init_db()
-- Tables: media_assets, stream_assets, subtitle_candidates,
--         benchmark_runs, review_tasks

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS media_assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash    TEXT    NOT NULL UNIQUE,
    file_path     TEXT    NOT NULL,
    file_name     TEXT    NOT NULL,
    duration_sec  REAL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

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

CREATE TABLE IF NOT EXISTS subtitle_candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash      TEXT    NOT NULL,
    source_id       TEXT    NOT NULL,   -- SubtitleCandidate.id e.g. 'asr_ja'
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_media_assets_hash ON media_assets(media_hash);
CREATE INDEX IF NOT EXISTS idx_stream_assets_media ON stream_assets(media_asset_id);
CREATE INDEX IF NOT EXISTS idx_candidates_media ON subtitle_candidates(media_hash);
CREATE INDEX IF NOT EXISTS idx_candidates_source ON subtitle_candidates(source_id, model_version);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON subtitle_candidates(status);
CREATE INDEX IF NOT EXISTS idx_benchmark_media ON benchmark_runs(media_hash);
CREATE INDEX IF NOT EXISTS idx_review_tasks_candidate ON review_tasks(candidate_id);
CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review_tasks(status);
