# Epic 05 — Library-scale automation

**Status:** `batch_process.py` / `core/runtime/batch_process.py` can scan a
directory, skip existing SRTs, and watch for new files. This is a batch script,
not a queue platform. Durable queue state, retry/resume, status reporting, and
safe concurrency are all missing.

**Parent:** beckmt4/anime-subtitle-pipeline#25

**Backlog reference:** `docs/BACKLOG.md` Phase 6, item 33

---

## Tasks

### Task 05-A — Persistent processing queue (SQLite-backed)

**What:** Replace the in-memory batch loop with a durable queue so that
partially-processed libraries can resume after interruption.

**Schema:**

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `media_path` | TEXT UNIQUE | Stable canonical path |
| `media_hash` | TEXT | Stable content hash (e.g. xxHash of first 1 MB) |
| `state` | TEXT | `discovered`, `queued`, `running`, `completed`, `failed`, `review_required`, `approved`, `skipped` |
| `retry_count` | INTEGER | Default 0 |
| `error_reason` | TEXT | Last error message |
| `registry_run_id` | TEXT | Link to `ArtifactRegistry` run |
| `created_at` | TEXT | ISO timestamp |
| `updated_at` | TEXT | ISO timestamp |

**Acceptance criteria:**
- [ ] Queue table created automatically in the configured SQLite DB
- [ ] State transitions are logged: `discovered → queued → running → completed/failed`
- [ ] `review_required` state set when PolicyEngine routes output to review
- [ ] Queue is safe to read/write from a single worker process
- [ ] Tests cover all state transitions and duplicate prevention

---

### Task 05-B — Recursive library scanner

**What:** Replace flat directory listing with a recursive scanner that detects
media files, existing sidecar subtitles, and weak/missing English subtitles.

**Acceptance criteria:**
- [ ] Scans recursively under a root directory
- [ ] Detects: `.mkv`, `.mp4`, `.avi` (configurable extensions)
- [ ] Detects existing sidecar `.en.srt` files; marks those media as `skipped`
      unless `--force` is set
- [ ] Computes stable media hash per file to avoid re-queuing known files
- [ ] Does not re-queue items already in `completed` or `skipped` state
- [ ] Prints discovery summary (N found, M already complete, K queued)

---

### Task 05-C — Worker mode

**What:** A worker process that drains the queue, one file at a time, with
safe GPU locking.

**Acceptance criteria:**
- [ ] `python main.py --mode worker --worker-action run [--limit N]` — process
      up to N items from queue (default: no limit)
- [ ] `python main.py --mode worker --worker-action watch` — poll queue continuously
- [ ] `python main.py --mode worker --worker-action retry-failed` — requeue failed
      items (up to configurable max retries)
- [ ] `python main.py --mode worker --worker-action resume` — continue interrupted
      `running` items (set to `queued` and reprocess)
- [ ] GPU lock file prevents two workers from running concurrently
- [ ] Worker logs per-file duration and final state

---

### Task 05-D — Status / reporting CLI

**What:** A way to see the current queue state without reading the database directly.

**Acceptance criteria:**
- [ ] `python main.py --mode worker --worker-action status` prints count by state
- [ ] `python main.py --mode worker --worker-action failures` lists failed items
      with error reason
- [ ] `python main.py --mode worker --worker-action review-required` lists items
      pending human review
- [ ] Output is human-readable and also available as JSON (`--json` flag)

---

### Task 05-E — Artifact registry integration

**What:** Every processed file should create a registry run record, and queue
items should link to that record.

**Acceptance criteria:**
- [ ] Each worker-processed file creates a `run` record in `ArtifactRegistry`
- [ ] Queue item `registry_run_id` is populated after processing
- [ ] Failed items record the error in both the queue and the registry run

---

### Task 05-F — Tests

**Acceptance criteria:**
- [ ] Queue state transitions: discovered → queued → running → completed
- [ ] Duplicate scan prevention (same file path + hash not re-queued)
- [ ] Failed item retry up to max retries, then stays `failed`
- [ ] `review_required` state set and visible in status CLI
- [ ] Interrupted `running` item can be resumed
- [ ] All tests run without real media files (mocked filesystem)
