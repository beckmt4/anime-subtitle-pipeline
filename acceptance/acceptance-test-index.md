# Acceptance-Test Index

Maps every epic and its implementation tasks to the acceptance checklists and
test files that provide evidence of completion.

**How to maintain this index:** When you add a new `acceptance/*.md` file,
add a row to this table. The architecture guard test
`tests/test_architecture_guard.py::TestAcceptanceIndexCompleteness` will fail
CI if a new acceptance file is not referenced here.

---

## Platform architecture and CI foundation

| Issue | Acceptance file | Key test files | Status |
|-------|----------------|----------------|--------|
| #15 — Platform re-architecture | `acceptance/15-platform-rearchitecture.md` | `tests/test_config.py`, `tests/test_models_and_inspect.py` | Phase-1 met |
| #33 — Real tests + CI | `acceptance/33-real-tests-and-ci.md` | All CI test files | Met |

---

## Phase 0 — Persistence, deployment, and maintenance

| Issue | Acceptance file | Key test files | Status |
|-------|----------------|----------------|--------|
| Subtitle corrector drift detection (#35) | `acceptance/35-subtitle-corrector-drift-detection.md` | `tests/test_subtitle_corrector.py` | Met |
| Subtitle pipeline entrypoint (#37) | `acceptance/37-subtitle-pipeline-entrypoint.md` | `tests/test_subtitle_pipeline.py` | Met |
| Embedded EN subtitle detection (#38) | `acceptance/38-embedded-en-detection.md` | `tests/test_source_selection.py` | Met |
| LLM polish drift guard (#38) | `acceptance/38-llm-polish-drift-guard.md` | `tests/test_llm_polish_drift.py` | Met |
| Generate mode LLM polish no-change (#40) | `acceptance/40-generate-mode-llm-polish-no-change.md` | `tests/test_orchestrator.py` | Met |

---

## Phase 1 — Generate-mode hardening

| Issue | Acceptance file | Key test files | Status |
|-------|----------------|----------------|--------|
| #52 — Explainable source-selection report | `acceptance/52-explainable-source-selection-report.md` | `tests/test_source_selection.py`, `tests/test_orchestrator.py` | Met |
| #53 — Generate inspect-only | `acceptance/53-generate-inspect-only.md` | `tests/test_orchestrator.py` | Met |
| #54 — Candidate confidence scoring | `acceptance/54-candidate-confidence-scoring.md` | `tests/test_asr_warning_routing.py`, `tests/test_candidate_pipeline.py` | Met |
| #80 — ASR confidence handling | `acceptance/80-asr-confidence-handling.md` | `tests/test_asr_quality_propagation.py`, `tests/test_asr_warning_routing.py` | Met |

---

## Phase 2 — Translation quality engine upgrade

| Issue | Acceptance file | Key test files | Status |
|-------|----------------|----------------|--------|
| #74 — Direct LLM translation engine | `acceptance/74-direct-llm-translation-engine.md` | `tests/test_translation_engine_selector.py` | Met |
| #75 — Translation engine selector + hybrid | `acceptance/75-translation-engine-selector.md` | `tests/test_translation_engine_selector.py` | Met |
| #76 — Two-pass translation workflow | `acceptance/two-pass-translation-workflow.md` | `tests/test_two_pass_translation.py` | Met |
| #77 — Live-action / adult profile | `acceptance/77-live-action-adult-profile.md` | `tests/test_translation_engine_selector.py` | Met |
| #79 — Translation QC judge | `acceptance/79-translation-qc-judge.md` | `tests/test_translation_qc.py`, `tests/test_translation_qc_judge.py` | Met |
| #81 — Model/hardware evaluation matrix | `acceptance/81-model-hardware-evaluation.md` | `tests/test_models_and_inspect.py` | Met |
| #134 — Pack glossary/name enforcement | `acceptance/134-pack-glossary-name-enforcement.md` | `tests/test_translation_glossary.py` | Met |
| #136 — Translation memory | `acceptance/136-translation-memory-approved-corrections.md` | `tests/test_translation_memory.py` | Met |
| #137 — Translation dataset export | `acceptance/137-review-correction-dataset-exports.md` | `tests/test_translation_dataset_export.py` | Met |
| #78 — Translation benchmark corpus | _(not yet created)_ | _(pending)_ | **Outstanding** — see `specs/epics/epic-02-translation-quality.md` |

---

## Phase 3 — Benchmark hardening and review routing

| Issue | Acceptance file | Key test files | Status |
|-------|----------------|----------------|--------|
| #20 — Benchmark mode hardening | _(covered inline in PR)_ | `tests/test_benchmark.py`, `tests/test_benchmark_generalized.py`, `tests/test_benchmark_hardening.py` | Met |
| #56 / #82 — Review-task generation rules | `acceptance/82-review-task-generation-rules.md` | `tests/test_review_task_routing.py` | Met |
| #22 — Human review queue and local review UI | _(not yet created; MVP backbone only)_ | `tests/test_review_workflow.py` | **Partial** — see `specs/epics/epic-04-review-workflow.md` |

---

## Phase 4 — Subtitle source completeness (OCR)

| Issue | Acceptance file | Key test files | Status |
|-------|----------------|----------------|--------|
| #21 — OCR CLI wiring | `acceptance/21-bitmap-ocr-cli-wiring.md` | `tests/test_main_ocr_wiring.py`, `tests/test_ocr_sidecar_support.py` | Met (wiring); product backend **outstanding** — see `specs/epics/epic-03-ocr-capability.md` |

---

## Phase 5 — Domain packs

| Issue | Acceptance file | Key test files | Status |
|-------|----------------|----------------|--------|
| #29 — Language pack interface | `acceptance/29-language-pack-interface.md` | `tests/test_packs_language_ja_en.py` | Met |
| #30 — Domain pack interface | `acceptance/30-domain-pack-interface.md` | `tests/test_packs_domain.py` | Met |
| #23 — Anime domain pack v1 | _(not yet created)_ | _(pending)_ | **Outstanding** — see `specs/epics/epic-06-anime-domain-pack.md` |
| #24 — JAV domain pack v1 | _(not yet created)_ | _(pending)_ | **Outstanding** — see `specs/epics/epic-06-anime-domain-pack.md` |

---

## Phase 6 — Library-scale automation

| Issue | Acceptance file | Key test files | Status |
|-------|----------------|----------------|--------|
| #25 — Queue + library automation | _(not yet created)_ | `tests/test_batch_process.py` (batch script only) | **Outstanding** — see `specs/epics/epic-05-library-automation.md` |

---

## Phase 7 — Multi-language architecture and expansion

| Issue | Acceptance file | Key test files | Status |
|-------|----------------|----------------|--------|
| #55 — Language-pack routing hooks | `acceptance/language-pack-routing-hooks.md` | `tests/test_orchestrator.py`, `tests/test_packs_language_ja_en.py` | Met |
| #26 — Language-pack architecture | `acceptance/epic-language-pack-architecture.md` | `tests/test_packs_language_expansions.py`, `tests/test_packs_language_ja_en.py` | Met |
| #27 — First non-Japanese expansions | _(not yet created)_ | _(pending)_ | **Outstanding** — see `specs/epics/epic-07-multi-language-proof.md` |

---

## Phase 8 — CI, test, and release hardening

| Capability | Acceptance file | Key test files | Status |
|-----------|----------------|----------------|--------|
| Architecture guards | _(this index + test file)_ | `tests/test_architecture_guard.py` | Met |
| Product-readiness doc + release gates | _(docs)_ | `docs/product-readiness.md` | Met |
| Smoke tests | _(not yet created)_ | _(pending)_ | **Outstanding** — see `specs/epics/epic-08-ci-hardening.md` |
| Hardcoded-ja/en guards in core/mt | _(stubbed in test_architecture_guard.py)_ | `tests/test_architecture_guard.py` (skipped) | **Pending Epic 07 Task C** |
