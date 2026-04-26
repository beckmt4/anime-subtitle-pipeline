# #51 — Schema design

**Status:** implemented  
**PR:** #58 (initial registry), this issue (artifacts + lineage + pipeline runs)

---

## Problem

The codebase is file-driven.  Every pipeline run produces `.srt`, `.mkv`, and
QC JSON files that are discarded or overwritten on the next run.  There is no
persistent record of:

- which media files have been processed and when
- which subtitle candidates were accepted or rejected
- why a candidate was sent back for reprocessing
- how a final subtitle track was derived from an ASR run → MT pass → LLM polish
- what output files (SRTs, burned-in MKV) exist for a given media file
- the history of a complete pipeline execution

Without a written schema, the project would accumulate ad-hoc JSON files and
incompatible state formats.

---

## Scope

**In scope**

- `media_assets` — tracked input media files
- `stream_assets` — individual audio / subtitle / video streams within a container
- `subtitle_candidates` — every subtitle track produced (ASR, MT, LLM-polished)
- `pipeline_runs` — one record per end-to-end pipeline invocation
- `artifacts` — output files (SRT, burned-in MKV, QC JSON) linked to candidates
- `benchmark_runs` — WER / BLEU / chrF snapshots comparing two candidates
- `review_tasks` — human or automated review decisions on candidates
- candidate lineage: `parent_candidate_id` FK so ASR → MT → LLM chains can be traced

**Out of scope**

- Segment-level storage (segments stay serialised as JSON blobs for now)
- Multi-user auth / row-level security
- Cloud sync
- Schema versioning beyond simple `ALTER TABLE` migrations

---

## Design

### Tables

```
media_assets
  id, media_hash (unique), file_path, file_name, duration_sec,
  created_at, updated_at

stream_assets
  id, media_asset_id → media_assets.id,
  stream_index, stream_type, language, codec, title, created_at

subtitle_candidates
  id, media_hash, source_id, model_version, language, source,
  origin_stream, parent_candidate_id → subtitle_candidates.id,   ← lineage
  segments_json, meta_json,
  status (pending|accepted|failed|review_required),
  created_at, updated_at

pipeline_runs
  id, run_id (unique), media_hash,
  status (running|completed|failed|cancelled),
  config_json, started_at, finished_at, error_message

artifacts
  id, media_hash, candidate_id → subtitle_candidates.id,
  pipeline_run_id → pipeline_runs.id,
  artifact_type (srt|mkv_burned|qc_json|benchmark_json),
  file_path, file_hash, version, created_at

benchmark_runs
  id, media_hash, run_id (unique),
  reference_candidate_id → subtitle_candidates.id,
  hypothesis_candidate_id → subtitle_candidates.id,
  wer, bleu, chrf, metrics_json, created_at

review_tasks
  id, media_hash, candidate_id → subtitle_candidates.id,
  status (pending|approved|rejected|reprocess),
  reprocess_reason, reviewer_notes, created_at, updated_at
```

### Candidate lineage

The `parent_candidate_id` column on `subtitle_candidates` enables tracing the
full processing chain:

```
asr_ja  (source='asr',    parent=NULL)
  └─ mt_en   (source='mt',    parent=asr_ja.id)
       └─ mt_llm_en (source='mt_llm', parent=mt_en.id)
```

The leaf candidate (`mt_llm_en`) is what gets written to an SRT and stored as
an artifact.

### Artifacts

One row per output file.  The `version` column starts at 1 and increments when
the same candidate produces a second output (e.g. after a reprocess).
`file_hash` is a SHA-256 digest of the output file content so drift can be
detected if files are edited externally.

`artifact_type` values:
- `srt` — plain-text subtitle file
- `mkv_burned` — video with hard-coded subtitles
- `qc_json` — output of `subtitle_qc.validate_srt_file()`
- `benchmark_json` — per-run metrics snapshot

### Pipeline runs

One row per top-level pipeline invocation (one `main.py` call or one n8n
workflow trigger).  `config_json` snapshots the effective config at run time so
results are reproducible.  `finished_at` is NULL while the run is still active.

### Indexes

```sql
-- media_assets
CREATE UNIQUE INDEX ON media_assets(media_hash);

-- subtitle_candidates
CREATE INDEX ON subtitle_candidates(media_hash);
CREATE INDEX ON subtitle_candidates(source_id, model_version);
CREATE INDEX ON subtitle_candidates(status);
CREATE INDEX ON subtitle_candidates(parent_candidate_id);

-- pipeline_runs
CREATE UNIQUE INDEX ON pipeline_runs(run_id);
CREATE INDEX ON pipeline_runs(media_hash);
CREATE INDEX ON pipeline_runs(status);

-- artifacts
CREATE INDEX ON artifacts(media_hash);
CREATE INDEX ON artifacts(candidate_id);
CREATE INDEX ON artifacts(pipeline_run_id);
CREATE INDEX ON artifacts(artifact_type);

-- review_tasks
CREATE INDEX ON review_tasks(candidate_id);
CREATE INDEX ON review_tasks(status);
```

---

## Mapping: file outputs → persisted records

| File output today | Future persisted record |
|---|---|
| `*.srt` written to `outbox/` | `artifacts` row, `artifact_type='srt'` |
| `*_burned.mkv` from `srt_writer.py` | `artifacts` row, `artifact_type='mkv_burned'` |
| QC JSON from `subtitle_qc.py` | `artifacts` row, `artifact_type='qc_json'` |
| `benchmark_results.json` | `benchmark_runs` row + `artifacts` row |
| ASR segments list | `subtitle_candidates` row, `source='asr'` |
| MT-translated segments | `subtitle_candidates` row, `source='mt'`, `parent_candidate_id=asr.id` |
| LLM-polished segments | `subtitle_candidates` row, `source='mt_llm'`, `parent_candidate_id=mt.id` |
| `error_log.txt` | `pipeline_runs.error_message` + `status='failed'` |

---

## Acceptance criteria

- [x] schema covers media, streams, candidates, benchmark runs, review tasks
- [x] `artifacts` table tracks every output file with type, path, hash, version
- [x] `pipeline_runs` table tracks every top-level invocation
- [x] `parent_candidate_id` on `subtitle_candidates` enables lineage tracing
- [x] candidate lineage: source → MT → LLM chain is representable
- [x] benchmark runs reference candidate records via FK
- [x] review tasks reference candidate records via FK
- [x] migration SQL committed in `docs/migrations/`
- [x] all new tables covered by unit tests

---

## Open questions (resolved)

**Q: `state_transitions` table vs `pipeline_runs`?**  
Resolved: `pipeline_runs` with `status` + `error_message` is sufficient for now.
A separate `state_transitions` audit log can be added in a later issue if the
review workflow requires fine-grained history.

**Q: FK from `subtitle_candidates.media_hash` to `media_assets`?**  
Deferred.  The natural key relationship is enforced by convention at the
application layer.  Adding a real FK would require media assets to be created
before any candidate is stored, which is a bigger workflow change.

**Q: Segment-level table?**  
Out of scope.  JSON blobs are sufficient for current query patterns.
