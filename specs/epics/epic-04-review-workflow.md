# Epic 04 — Review workflow beta hardening

**Status:** MVP backbone implemented (`core/review/workflow.py`,
`core/review/routing.py`). Queue, render, and approve flows work in tests.
UX, CLI polish, approved-output lifecycle, and review task deduplication
need hardening before this is a usable local product.

**Parent:** beckmt4/anime-subtitle-pipeline#22

**Backlog reference:** `docs/BACKLOG.md` Phase 3, item 28

---

## Tasks

### Task 04-A — Review CLI polish

**What:** The review mode flags (`--review-action queue/render/approve`) work
but are not ergonomic. The goal is clear subcommand UX.

**Acceptance criteria:**
- [ ] `python main.py --mode review --review-action queue` lists pending tasks
      with ID, media path, reason codes, and score
- [ ] `python main.py --mode review --review-action render --task-id N` generates
      HTML review file and prints path to stdout
- [ ] `python main.py --mode review --review-action approve --task-id N
      --review-edits-json edits.json` applies edits and writes approved SRT
- [ ] `python main.py --mode review --review-action reject --task-id N` marks
      task rejected with optional reason
- [ ] `python main.py --mode review --review-action export-memory` exports approved
      corrections to translation memory
- [ ] All actions print human-readable confirmation to stdout
- [ ] Invalid task IDs and missing files produce clear error messages (not tracebacks)

---

### Task 04-B — Review UI improvements

**What:** The existing HTML review UI is static. It needs to surface the
information a human needs to make a review decision.

**Acceptance criteria:**
- [ ] Candidate score visible per review task
- [ ] QC findings shown per segment (subtitle QC + translation QC codes)
- [ ] ASR confidence warnings highlighted per segment
- [ ] OCR confidence warnings highlighted per segment (when applicable)
- [ ] Translation QC codes (`possible_omission`, `cjk_leakage`, etc.) shown inline
- [ ] The edit export JSON format is clearly described in the UI or a tooltip
- [ ] Export instructions are present in the rendered HTML

---

### Task 04-C — Approved-output lifecycle

**What:** Approved SRTs are written, but there is no concept of an approved
artifact being the preferred output for that media file.

**Acceptance criteria:**
- [ ] Approved SRT is registered as a `preferred` artifact in `ArtifactRegistry`
- [ ] `run_generate()` checks for an existing approved artifact and skips
      re-generation when one is found (or reports it as the selected output)
- [ ] Parent/child candidate relationship (original → approved) is recorded in registry
- [ ] `review --review-action re-approve --task-id N` allows re-approving an
      already-approved task after further edits

---

### Task 04-D — Translation memory quality gates

**What:** Currently, any non-empty edit is stored to translation memory.
Low-quality or no-op edits should not pollute the memory.

**Acceptance criteria:**
- [ ] Empty or whitespace-only edits are not stored
- [ ] Edits that are identical to the original output are not stored
- [ ] Each stored correction includes: source text, prior output, approved output,
      domain, language pack ID, context segments
- [ ] A minimum edit distance threshold is configurable

---

### Task 04-E — Review task deduplication and state machine

**What:** Submitting the same media file twice can create duplicate pending tasks.
Review tasks have no explicit state machine.

**Acceptance criteria:**
- [ ] States defined: `pending`, `approved`, `rejected`, `superseded`
- [ ] Re-running generate for a file with a pending review task does not create
      a duplicate; it either supersedes or skips
- [ ] `queue` command shows state for each task
- [ ] Tests cover: approve, reject, supersede, duplicate prevention

---

### Task 04-F — Tests

**Acceptance criteria:**
- [ ] Approval with edits → approved SRT written, corrections stored to memory
- [ ] Approval without edits → approved SRT written, no memory write
- [ ] Rejection → task marked rejected, no SRT written
- [ ] Invalid segment index in edits JSON → error, no partial write
- [ ] Memory write stores correct source/prior/approved/domain fields
- [ ] Artifact creation on approval verified
