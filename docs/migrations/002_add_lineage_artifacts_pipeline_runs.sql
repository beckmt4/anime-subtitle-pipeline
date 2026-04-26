-- Migration 002 — candidate lineage, pipeline runs, artifacts
-- Issue: #51 — Schema design
-- Applied by: core/artifacts/schema.py _apply_migrations() +
--             new CREATE TABLE IF NOT EXISTS in init_db()

PRAGMA foreign_keys=ON;

-- 1. Candidate lineage: trace ASR → MT → LLM-polish chains
ALTER TABLE subtitle_candidates
    ADD COLUMN parent_candidate_id INTEGER REFERENCES subtitle_candidates(id);

CREATE INDEX IF NOT EXISTS idx_candidates_parent
    ON subtitle_candidates(parent_candidate_id);

-- 2. Pipeline runs: one row per top-level pipeline invocation
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    NOT NULL UNIQUE,
    media_hash      TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'running',
        -- 'running' | 'completed' | 'failed' | 'cancelled'
    config_json     TEXT    NOT NULL DEFAULT '{}',
    started_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_media
    ON pipeline_runs(media_hash);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status
    ON pipeline_runs(status);

-- 3. Artifacts: every output file (SRT, burned MKV, QC JSON, benchmark JSON)
CREATE TABLE IF NOT EXISTS artifacts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    media_hash       TEXT    NOT NULL,
    artifact_type    TEXT    NOT NULL,
        -- 'srt' | 'mkv_burned' | 'qc_json' | 'benchmark_json'
    file_path        TEXT    NOT NULL,
    candidate_id     INTEGER REFERENCES subtitle_candidates(id) ON DELETE SET NULL,
    pipeline_run_id  INTEGER REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    file_hash        TEXT,               -- SHA-256 of the output file content
    version          INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_artifacts_media
    ON artifacts(media_hash);
CREATE INDEX IF NOT EXISTS idx_artifacts_candidate
    ON artifacts(candidate_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_pipeline_run
    ON artifacts(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_type
    ON artifacts(artifact_type);
