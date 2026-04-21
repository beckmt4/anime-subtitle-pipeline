# dev-real-tests-and-ci

**Purpose:** Bootstrap real deterministic unit tests and GitHub Actions CI for an
anime subtitle pipeline that previously had only smoke scripts requiring live services.

**Used in:** Issue #33 / PR for "replace smoke-script-only validation with real tests + CI"
**Tool:** Claude Code (claude-sonnet-4-6)

---

## Prompt

```
We are working in this repo: https://github.com/beckmt4/anime-subtitle-pipeline

Task: Replace smoke-script-only validation as the main merge gate with real
deterministic unit tests and GitHub Actions CI, while keeping `test_pipeline.py`
as manual system validation.

Non-negotiable repo-process rules:
1. Open or reference an issue before starting significant work.
2. Check `specs/` first. If no relevant spec exists, create one.
3. Add tests before or alongside code changes.
4. Use `pytest`. New tests go under `tests/`.
5. Put stable deterministic fixtures in `fixtures/`.
6. Create or update an acceptance artifact in `acceptance/`.
7. Save this prompt in `prompts/`.
8. Do not claim anything was tested unless you actually ran it.
9. Check `docs/architecture/module-boundaries.md` for any arch-affecting change.

Primary required outcomes:
- Create a GitHub issue (or issue markdown if gh not authenticated)
- Keep `test_pipeline.py` as manual system validation
- Add real unit tests for: media_inspect, compare_core, config loading,
  source selection, constraint enforcement
- Add a GitHub Actions CI workflow for lint + tests
- Add small deterministic fixtures that do not require model downloads

Constraints:
- No CI dependency on ffmpeg, Whisper, Ollama, or live local services
- Prefer pure unit tests with mocks/stubs at runtime boundaries
- If code imports heavy ML packages (faster_whisper, torch, transformers,
  opentelemetry) at module level, stub them in conftest.py using sys.modules
  setdefault so CI can load the modules without installing GPU packages
- Do not add broad unrelated refactors
- Integration tests must be marked @pytest.mark.integration

Deliverables:
1. Issue URL or issue markdown file path + gh command
2. Spec file path
3. Acceptance file path
4. Prompt file path
5. Summary of what changed
6. Files added/modified
7. Exact local commands for lint and tests
8. What was actually run vs not run
9. Follow-up work needed
```

---

## Notes

**What worked:**
- `sys.modules.setdefault` in `tests/conftest.py` cleanly stubs heavy ML deps
  without interfering when packages are actually installed on the dev machine.
- Testing private orchestrator helpers (`_lang_matches`, `_first_text_sub`,
  `_first_audio_order`) directly gives high-value coverage of the decision tree
  without requiring any mocking of IO or model loading.
- Mocking jiwer/sacrebleu via `patch.dict("sys.modules", ...)` inside individual
  test methods avoids CI dependency while still testing the call contract.
- `flake8 --select=E9,F --extend-ignore=F401,F841` provides useful CI lint
  (syntax errors, undefined names) without requiring a style migration.

**What to watch for:**
- If `opentelemetry` is updated or split into more subpackages, the stub list in
  `conftest.py` may need expanding.
- The conftest stub approach works because none of the tested functions actually
  *call* faster_whisper/torch at test time — they just need the imports to succeed.
- config.py's `asr_device` property lazily imports `torch` only when device="auto".
  Test configs must set `device: cpu` to avoid triggering this.

**Recommended follow-up:**
- Fix pre-existing F401/F841 flake8 violations in a separate chore PR.
- Add integration test markers to root-level test scripts.
- Migrate root test scripts to `tests/` as modules are refactored into `core/`.
