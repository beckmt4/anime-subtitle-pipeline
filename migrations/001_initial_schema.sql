-- migrations/001_initial_schema.sql
--
-- Initial schema for the anime-subtitle-pipeline artifact registry.
-- Covers: media_assets, stream_assets, subtitle_candidates, benchmark_runs,
--         benchmark_comparisons, review_tasks, review_task_candidates,
--         artifacts, state_transitions.
--
-- Designed for SQLite >= 3.25 (window functions, WITH RECURSIVE).
-- Apply once on a fresh database.  For existing databases that already have
-- some of these tables (created by core/artifacts/schema.py), see the
-- forward-compatibility notes at the bottom of this file.
--
-- Usage:
--   sqlite3 artifacts.db < migrations/001_initial_schema.sql
--
-- ---------------------------------------------------------------------------

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- media_assets
--   Root entity.  One row per unique media file (keyed by SHA-256 content hash).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media_assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash    TEXT    NOT NULL UNIQUE,   -- SHA-256 hex of file content
    file_path     TEXT    NOT NULL,          -- absolute or relative path
    file_name     TEXT    NOT NULL,          -- basename
    duration_sec  REAL,                      -- total duration in seconds (nullable)
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- stream_assets
--   Per-stream metadata for every audio/subtitle/video track inside a container.
--   Populated from ffprobe output at ingest time.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stream_assets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    media_asset_id  INTEGER NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
    stream_index    INTEGER NOT NULL,
    stream_type     TEXT    NOT NULL,   -- 'audio' | 'subtitle' | 'video'
    language        TEXT,               -- ISO 639-1 / BCP-47 if known
    codec           TEXT,               -- e.g. 'aac', 'ass', 'h264'
    title           TEXT,               -- stream title metadata if present
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- subtitle_candidates
--   Every subtitle variant produced or derived for a media file.
--   source discriminates the origin:
--     'asr'      — Whisper / ASR engine output
--     'embedded' — subtitle stream extracted from the container
--     'mt'       — machine-translation of an ASR or embedded candidate
--     'mt_llm'   — LLM-polished version of an MT candidate
--
--   Lineage: parent_candidate_id forms a chain from source to final output.
--   NULL means the candidate is a primary source (asr / embedded).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subtitle_candidates (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash           TEXT    NOT NULL,
    source_id            TEXT    NOT NULL,   -- pipeline-assigned ID e.g. 'asr_ja'
    model_version        TEXT    NOT NULL DEFAULT '',   -- model/version string
    language             TEXT    NOT NULL,   -- ISO 639-1
    source               TEXT    NOT NULL,   -- 'asr' | 'embedded' | 'mt' | 'mt_llm'
    origin_stream        TEXT    NOT NULL,   -- 'audio:0', 'sub:1', filename, …
    parent_candidate_id  INTEGER REFERENCES subtitle_candidates(id),
        -- NULL for source candidates; set for MT/LLM-derived to trace lineage
    segments_json        TEXT    NOT NULL DEFAULT '[]',   -- JSON array of segment dicts
    meta_json            TEXT    NOT NULL DEFAULT '{}',   -- arbitrary metadata
    status               TEXT    NOT NULL DEFAULT 'pending',
        -- 'pending' | 'accepted' | 'failed' | 'review_required'
    created_at           TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- benchmark_runs
--   One row per benchmark execution comparing a reference candidate against a
--   hypothesis candidate.  Top-level metric values are denormalised for fast
--   sorting; the full metrics dict lives in metrics_json.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS benchmark_runs (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash              TEXT    NOT NULL,
    run_id                  TEXT    NOT NULL UNIQUE,   -- UUID or slug assigned by caller
    reference_candidate_id  INTEGER REFERENCES subtitle_candidates(id),
    hypothesis_candidate_id INTEGER REFERENCES subtitle_candidates(id),
    wer                     REAL,       -- Word Error Rate (lower is better)
    bleu                    REAL,       -- BLEU score (higher is better)
    chrf                    REAL,       -- chrF score (higher is better)
    metrics_json            TEXT    NOT NULL DEFAULT '{}',   -- full metrics blob
    created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- benchmark_comparisons
--   One row per (benchmark_run × metric).  Normalises the metrics_json blob
--   into queryable rows and ties each comparison back to the exact candidate
--   pair it measures.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS benchmark_comparisons (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_run_id        INTEGER NOT NULL REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    reference_candidate_id  INTEGER NOT NULL REFERENCES subtitle_candidates(id),
    hypothesis_candidate_id INTEGER NOT NULL REFERENCES subtitle_candidates(id),
    metric_name             TEXT    NOT NULL,   -- 'wer' | 'bleu' | 'chrf' | …
    metric_value            REAL    NOT NULL,
    meta_json               TEXT    NOT NULL DEFAULT '{}',
    created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- review_tasks
--   Human review decisions for subtitle candidates.
--   candidate_id is the primary (or sole) candidate under review.
--   For multi-candidate review, additional candidates are linked via
--   review_task_candidates.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS review_tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash        TEXT    NOT NULL,
    candidate_id      INTEGER NOT NULL REFERENCES subtitle_candidates(id) ON DELETE CASCADE,
        -- primary candidate; see review_task_candidates for multi-candidate tasks
    status            TEXT    NOT NULL DEFAULT 'pending',
        -- 'pending' | 'approved' | 'rejected' | 'reprocess'
    reprocess_reason  TEXT,   -- required when status = 'reprocess'
    reviewer_notes    TEXT,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- review_task_candidates
--   Join table — allows a single review task to cover multiple candidates
--   (e.g. "compare ASR-only vs MT-polished before deciding").
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS review_task_candidates (
    review_task_id  INTEGER NOT NULL REFERENCES review_tasks(id) ON DELETE CASCADE,
    candidate_id    INTEGER NOT NULL REFERENCES subtitle_candidates(id) ON DELETE CASCADE,
    PRIMARY KEY (review_task_id, candidate_id)
);

-- ---------------------------------------------------------------------------
-- artifacts
--   Versioned output files (e.g. .srt, .ass) produced for a subtitle candidate.
--   version increments on reprocess; old versions are kept with status='superseded'.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS artifacts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id    INTEGER NOT NULL REFERENCES subtitle_candidates(id) ON DELETE CASCADE,
    media_hash      TEXT    NOT NULL,
    artifact_type   TEXT    NOT NULL,   -- 'srt' | 'ass' | 'vtt' | 'json' | 'raw'
    file_path       TEXT    NOT NULL,
    file_hash       TEXT    NOT NULL,   -- SHA-256 of artifact file content
    version         INTEGER NOT NULL DEFAULT 1,
        -- increments per (candidate_id, artifact_type) on reprocess
    status          TEXT    NOT NULL DEFAULT 'active',
        -- 'active' | 'superseded' | 'deleted'
    meta_json       TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- state_transitions
--   Audit log for every status change on subtitle_candidates, review_tasks,
--   and artifacts.  entity_type + entity_id identify the row being changed.
--   from_status is NULL for the initial creation event.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS state_transitions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type  TEXT    NOT NULL,   -- 'subtitle_candidate' | 'review_task' | 'artifact'
    entity_id    INTEGER NOT NULL,
    from_status  TEXT,               -- NULL for initial creation
    to_status    TEXT    NOT NULL,
    reason       TEXT,               -- free-text reason (e.g. reprocess reason)
    actor        TEXT,               -- system component or user name
    meta_json    TEXT    NOT NULL DEFAULT '{}',
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- media_assets
CREATE INDEX IF NOT EXISTS idx_media_assets_hash
    ON media_assets(media_hash);

-- stream_assets
CREATE INDEX IF NOT EXISTS idx_stream_assets_media
    ON stream_assets(media_asset_id);

-- subtitle_candidates
CREATE INDEX IF NOT EXISTS idx_candidates_media
    ON subtitle_candidates(media_hash);
CREATE INDEX IF NOT EXISTS idx_candidates_parent
    ON subtitle_candidates(parent_candidate_id);
CREATE INDEX IF NOT EXISTS idx_candidates_source
    ON subtitle_candidates(source_id, model_version);
CREATE INDEX IF NOT EXISTS idx_candidates_status
    ON subtitle_candidates(status);

-- benchmark_runs
CREATE INDEX IF NOT EXISTS idx_benchmark_media
    ON benchmark_runs(media_hash);

-- benchmark_comparisons
CREATE INDEX IF NOT EXISTS idx_benchmark_comparisons_run
    ON benchmark_comparisons(benchmark_run_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_comparisons_ref
    ON benchmark_comparisons(reference_candidate_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_comparisons_hyp
    ON benchmark_comparisons(hypothesis_candidate_id);

-- review_tasks
CREATE INDEX IF NOT EXISTS idx_review_tasks_candidate
    ON review_tasks(candidate_id);
CREATE INDEX IF NOT EXISTS idx_review_tasks_status
    ON review_tasks(status);

-- artifacts
CREATE INDEX IF NOT EXISTS idx_artifacts_candidate
    ON artifacts(candidate_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_media
    ON artifacts(media_hash);
CREATE INDEX IF NOT EXISTS idx_artifacts_status
    ON artifacts(status);

-- state_transitions
CREATE INDEX IF NOT EXISTS idx_state_transitions_entity
    ON state_transitions(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_state_transitions_created
    ON state_transitions(created_at);

-- ---------------------------------------------------------------------------
-- Forward-compatibility notes
--
-- If applying this migration to a database that was already initialised by
-- core/artifacts/schema.py (which created the first 5 tables without
-- parent_candidate_id, benchmark_comparisons, review_task_candidates,
-- artifacts, or state_transitions), run the following ALTER TABLE statements
-- manually — or rely on the automatic migration in core/artifacts/schema.py
-- which applies them idempotently via the _MIGRATIONS list:
--
--   ALTER TABLE subtitle_candidates ADD COLUMN
--       parent_candidate_id INTEGER REFERENCES subtitle_candidates(id);
--
-- The other tables (benchmark_comparisons, review_task_candidates, artifacts,
-- state_transitions) are created with CREATE TABLE IF NOT EXISTS above and
-- will be added without conflict.
-- ---------------------------------------------------------------------------
