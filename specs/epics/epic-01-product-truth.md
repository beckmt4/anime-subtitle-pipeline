# Epic 01 — Product truth and roadmap reset (remaining tasks)

**Status:** Partially complete — FILE_OVERVIEW.md, PROJECT_SUMMARY.md,
product-readiness.md, BACKLOG.md, and architecture guard tests are done.
Remaining tasks are listed below.

**Parent:** Product truth and roadmap reset (problem statement Epic 1)

---

## Remaining tasks

### Task 01-A — Fix stale import examples in `docs/QUICK_REFERENCE.md`

**What:** `docs/QUICK_REFERENCE.md` contains code blocks that import from deleted
root shims:

```python
from config import Config
from mt import translate_candidate_jp_to_en
```

These modules no longer exist at the root. Imports should come from `core.*`.

**Acceptance criteria:**
- [ ] All code examples in `docs/QUICK_REFERENCE.md` import from `core.*`
- [ ] No references to `config.py`, `mt.py`, `asr.py`, `llm_polish.py`,
      `audio_utils.py`, or `srt_writer.py` as importable root modules
- [ ] `tests/test_architecture_guard.py` guard for QUICK_REFERENCE passes after fix

**Suggested fix locations:**
- `docs/QUICK_REFERENCE.md` lines ~287–290 (translate example)
- Any other code block referencing root shims

---

### Task 01-B — Fix stale import examples in `docs/API_DOCUMENTATION.md`

**What:** `docs/API_DOCUMENTATION.md` contains example code that uses the old
root-level API (`from mt import translate_candidate_jp_to_en`, etc.).

**Acceptance criteria:**
- [ ] All code examples in `docs/API_DOCUMENTATION.md` import from `core.*`
- [ ] No references to deleted root shims as importable modules
- [ ] `tests/test_architecture_guard.py` guard for API_DOCUMENTATION passes after fix

---

### Task 01-C — Verify GitHub issue state matches BACKLOG.md

**What:** Several GitHub issues were closed while child items remained unchecked,
and conversely several issues marked unchecked in BACKLOG.md have been implemented.
The master tracker issue (#15) may also be in a misleading state.

**Actions needed (manual, requires issue write access):**
- [ ] Reopen any GitHub issues that were closed prematurely (e.g. if child items
      are still unchecked without explicit deferral)
- [ ] Close GitHub issues whose acceptance criteria are met per `acceptance/`
      evidence (#74, #76, #77, #79, #56, #55, #26, #81)
- [ ] Update master tracker issue #15 to reflect current epic state
- [ ] Ensure every open issue maps to an entry in BACKLOG.md

**Note:** This task requires GitHub issue write access and cannot be automated
by the CI pipeline.
