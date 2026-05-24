# Epic 08 — CI, test, and release hardening (remaining tasks)

**Status:** CI runs on every push/PR (confirmed). Lint covers core + packs +
entrypoints. Architecture guard tests and acceptance-test index are now
implemented. Remaining gaps are listed below.

**Backlog reference:** `docs/BACKLOG.md` Phase 8, items 42–43

---

## Tasks

### Task 08-A — Consolidated smoke-test suite

**What:** Many individual test files provide implicit smoke coverage, but there
is no single explicit smoke-test module that an on-call developer can run to
verify the five core paths work end-to-end (with mocked models).

**Acceptance criteria:**
- [ ] `tests/test_smoke.py` exists with at least the following parameterized cases:
  1. **Inspect-only generate** — `run_generate(..., inspect_only=True)` returns
     source-selection metadata without calling ASR/MT/LLM
  2. **Text sidecar path** — mocked sidecar `.ja.srt` exists → MT → SRT output
  3. **Embedded subtitle mocked path** — mocked embedded EN subtitle track → SRT output
  4. **ASR mocked path** — mocked Faster-Whisper output → MT mocked → SRT output
  5. **MT mocked path** — mocked MarianMT → SRT output with QC sidecar
  6. **Review approval** — create review task, approve with edits, verify SRT written
- [ ] All smoke tests run in CI without GPU or model downloads
- [ ] `tests/test_smoke.py` is documented in `acceptance/acceptance-test-index.md`

---

### Task 08-B — Architecture guard: no hardcoded ja/en in core/mt

**What:** Once Epic 07 Task C removes the hardcoded Japanese strings from
`core/mt/__init__.py`, the architecture guard test should enforce that they
stay removed.

**Acceptance criteria:**
- [ ] `tests/test_architecture_guard.py` contains `test_no_hardcoded_japanese_prompt_in_core_mt`
- [ ] The guard checks that `core/mt/__init__.py` does not contain the literal string
      `"You are translating Japanese dialogue into English subtitles"`
- [ ] Guard also checks `core/polish/__init__.py` does not contain `text_ja` as a
      parameter name in public function signatures
- [ ] Guard is blocked by a `pytest.skip` with a message until Epic 07 Task C is done
      (to avoid false-fail before the refactor)

**Note:** This test should be added to `test_architecture_guard.py` as a skipped
test now so it becomes visible in the test output, and unskipped when Epic 07-C lands.

---

### Task 08-C — Acceptance-test index maintenance

**What:** `acceptance/acceptance-test-index.md` was created by this epic. It
should be updated whenever a new epic is closed or a new acceptance file is added.

**Acceptance criteria:**
- [ ] Each new `acceptance/*.md` file added in a PR also triggers an update to
      `acceptance/acceptance-test-index.md`
- [ ] The CI lint step or an architecture guard test fails if a new acceptance
      file exists that is not referenced in the index

**Implementation suggestion:** Add a Python test in `test_architecture_guard.py`
that reads the index and checks all `acceptance/*.md` files are referenced.

---

### Task 08-D — Branch protection and required CI

**What:** No branch protection rules are currently enforced. This means a
developer (or AI agent) could push directly to `main` without tests passing.

**Acceptance criteria (manual, requires repo admin access):**
- [ ] Branch protection rule on `main`: require CI workflow to pass before merge
- [ ] Branch protection rule on `main`: require at least 1 review on PRs
- [ ] README CI badge is prominent and reflects current CI status
- [ ] Documented in `CONTRIBUTING.md`

**Note:** This requires GitHub repository admin access and cannot be automated
via code changes.
