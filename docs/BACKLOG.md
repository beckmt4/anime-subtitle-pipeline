# Backlog tracker — ordered Subtitle Intelligence Platform roadmap

## Purpose
This is the repository-side copy of the top-level roadmap tracker expanding `anime-subtitle-pipeline` into a local-first subtitle intelligence platform for anime, JAV, and later multi-language media.

## Goals
- establish the platform architecture
- harden persistence, generate mode, and benchmark mode
- capture code-review cleanup work as actionable maintenance tickets
- add OCR and review workflows
- add anime and JAV domain packs
- add queue/batch automation
- introduce language-pack architecture for non-Japanese expansion

## Epic checklist
- [x] beckmt4/anime-subtitle-pipeline#16
- [x] beckmt4/anime-subtitle-pipeline#17
- [x] beckmt4/anime-subtitle-pipeline#18
- [x] beckmt4/anime-subtitle-pipeline#106
- [x] beckmt4/anime-subtitle-pipeline#19
- [x] beckmt4/anime-subtitle-pipeline#20
- [x] beckmt4/anime-subtitle-pipeline#73
- [ ] beckmt4/anime-subtitle-pipeline#21
- [ ] beckmt4/anime-subtitle-pipeline#22
- [ ] beckmt4/anime-subtitle-pipeline#23
- [ ] beckmt4/anime-subtitle-pipeline#24
- [ ] beckmt4/anime-subtitle-pipeline#25
- [ ] beckmt4/anime-subtitle-pipeline#26
- [ ] beckmt4/anime-subtitle-pipeline#27

## Current ordered backlog — work in this order

Treat epics as planning/tracking containers and child issues as executable work. Closed issues stay visible here as completed history, but the active queue starts at the first unchecked item.

### Phase 0 — Persistence, deployment, and maintenance hardening

Goal: finish the near-term registry/deployment foundation and clear actionable code-review cleanup before pulling more feature complexity forward.

1. [x] beckmt4/anime-subtitle-pipeline#85 — Add DB auto-migration runner on pipeline startup
2. [x] beckmt4/anime-subtitle-pipeline#82 — Wire ArtifactRegistry into `main.py` and orchestrator pipeline
3. [x] beckmt4/anime-subtitle-pipeline#86 — Add query API to ArtifactRegistry
4. [x] beckmt4/anime-subtitle-pipeline#87 — Surface `registry_run_id` in CLI output and Streamlit
5. [x] beckmt4/anime-subtitle-pipeline#83 — Expose pipeline run history via ProcessingLedger
6. [x] beckmt4/anime-subtitle-pipeline#107 — Allow `LLM_BASE_URL` env override for deployment configs
7. [x] beckmt4/anime-subtitle-pipeline#89 — Add `--timeout` flag to `subtitle_corrector.py` CLI
8. [x] beckmt4/anime-subtitle-pipeline#110 — Make subtitle_corrector drift noun detection case-insensitive
9. [x] beckmt4/anime-subtitle-pipeline#108 — Deprecate or remove legacy ASR-segment polish API in `llm_polish.py`
10. [x] beckmt4/anime-subtitle-pipeline#109 — Decide whether `subtitle_pipeline.py` is superseded and retire if unused
11. [x] beckmt4/anime-subtitle-pipeline#112 — Add `attic/README.md` explaining retired code policy
12. [x] beckmt4/anime-subtitle-pipeline#111 — Consolidate root documentation sprawl into `docs/`
13. [x] beckmt4/anime-subtitle-pipeline#84 — Track burned-in MKV artifacts in ArtifactRegistry

Parent epics for this phase:
- beckmt4/anime-subtitle-pipeline#18 — Add persistent state, artifact registry, and processing ledger
- beckmt4/anime-subtitle-pipeline#106 — Code review cleanup and deployment hardening backlog

### Phase 1 — Generate-mode hardening

Goal: make the current one-file workflow explainable, testable, and safe to trust before adding more model complexity.

14. [x] beckmt4/anime-subtitle-pipeline#52 — Add explainable source-selection report to generate mode
15. [x] beckmt4/anime-subtitle-pipeline#53 — Add generate-mode dry-run / inspect-only flow
16. [x] beckmt4/anime-subtitle-pipeline#54 — Add candidate confidence scoring and low-confidence thresholds to generate mode
17. [x] beckmt4/anime-subtitle-pipeline#80 — Add ASR confidence handling for difficult Japanese audio

Parent epic for this phase:
- beckmt4/anime-subtitle-pipeline#19 — Harden generate mode into a production-grade source selection engine

### Phase 2 — Translation-quality engine upgrade

Goal: remove MarianMT as the quality ceiling while keeping it as a baseline/fallback.

18. [x] beckmt4/anime-subtitle-pipeline#74 — Add direct context-aware LLM translation engine
19. [x] beckmt4/anime-subtitle-pipeline#75 — Add translation engine selector and hybrid routing
20. [x] beckmt4/anime-subtitle-pipeline#76 — Add literal-first and natural-subtitle second-pass workflow
21. [x] beckmt4/anime-subtitle-pipeline#79 — Add translation QC judge for omissions, drift, and register changes
22. [ ] beckmt4/anime-subtitle-pipeline#78 — Add translation benchmark corpus and model comparison reports
23. [x] beckmt4/anime-subtitle-pipeline#77 — Add live-action and adult-dialogue translation profile
24. [x] beckmt4/anime-subtitle-pipeline#81 — Add local model and hardware evaluation matrix for translation quality
25. [ ] (new) Generalize LLMDirectTranslator prompts — remove hardcoded "Japanese dialogue into English subtitles" from `core/mt/__init__.py`; spec: `specs/epics/epic-02-translation-quality.md`

Parent epic for this phase:
- beckmt4/anime-subtitle-pipeline#73 — Improve translation quality for anime, live-action, and difficult Japanese dialogue

### Phase 3 — Benchmark hardening and review routing

Goal: turn weak-output detection into actionable review tasks and repeatable quality reporting.

26. [x] beckmt4/anime-subtitle-pipeline#20 — Harden benchmark mode into a core product capability
27. [x] beckmt4/anime-subtitle-pipeline#56 — Create review-task generation rules for low-confidence generate and benchmark results
28. [ ] beckmt4/anime-subtitle-pipeline#22 — Build human review queue and local review UI (MVP backbone exists; UX hardening tracked in `specs/epics/epic-04-review-workflow.md`)

### Phase 4 — Subtitle source completeness

Goal: expand source support beyond ideal embedded text and ASR paths.

29. [x] beckmt4/anime-subtitle-pipeline#21 — Wire OCR backend into CLI generate/benchmark (done)
30. [ ] (new) OCR as real product capability — default backend, bitmap extraction pipeline, fixtures; spec: `specs/epics/epic-03-ocr-capability.md`

### Phase 5 — Domain packs

Goal: move anime/live-action/JAV behavior out of generic core and into explicit opt-in profiles/packs.

31. [ ] beckmt4/anime-subtitle-pipeline#23 — Create Anime domain pack v1; spec: `specs/epics/epic-06-anime-domain-pack.md`
32. [ ] beckmt4/anime-subtitle-pipeline#24 — Create JAV domain pack v1 with privacy-aware operation; spec: `specs/epics/epic-06-anime-domain-pack.md`

### Phase 6 — Library-scale automation

Goal: make the platform useful for batches and large media libraries after quality/review controls exist.

33. [ ] beckmt4/anime-subtitle-pipeline#25 — Add queue, batch processing, and library-scale automation; spec: `specs/epics/epic-05-library-automation.md`

### Phase 7 — Multi-language architecture and expansion

Goal: generalize the platform after the Japanese workflow is reliable.

34. [x] beckmt4/anime-subtitle-pipeline#55 — Refactor Japanese-only generate orchestration into language-pack routing hooks
35. [x] beckmt4/anime-subtitle-pipeline#26 — Introduce language-pack architecture for multi-language expansion
36. [ ] beckmt4/anime-subtitle-pipeline#27 — Add first non-Japanese language expansions; spec: `specs/epics/epic-07-multi-language-proof.md`

### Phase 8 — Product truth, docs, CI hardening

Goal: make docs and tracker tell the truth; make CI catch regressions.

37. [x] Fix docs/FILE_OVERVIEW.md — remove stale root-shim references
38. [x] Fix docs/PROJECT_SUMMARY.md — update file structure + API section
39. [x] Add docs/product-readiness.md — capability status map and release gates
40. [x] Add architecture guard tests (`tests/test_architecture_guard.py`)
41. [x] Add acceptance-test index (`acceptance/acceptance-test-index.md`)
42. [ ] Fix stale imports in `docs/QUICK_REFERENCE.md` and `docs/API_DOCUMENTATION.md`; spec: `specs/epics/epic-01-product-truth.md`
43. [ ] Consolidated smoke-test suite; spec: `specs/epics/epic-08-ci-hardening.md`

## Near-term next 10 issues

Start here unless there is a blocking bug:

1. beckmt4/anime-subtitle-pipeline#78 — Translation benchmark corpus and model comparison reports
2. beckmt4/anime-subtitle-pipeline#22 — Build human review queue and local review UI (harden MVP backbone)
3. (new) Generalize LLMDirectTranslator prompts — `specs/epics/epic-02-translation-quality.md`
4. (new) OCR product capability — `specs/epics/epic-03-ocr-capability.md`
5. beckmt4/anime-subtitle-pipeline#23 — Anime domain pack v1 — `specs/epics/epic-06-anime-domain-pack.md`
6. beckmt4/anime-subtitle-pipeline#25 — Library-scale automation — `specs/epics/epic-05-library-automation.md`
7. beckmt4/anime-subtitle-pipeline#27 — First non-Japanese language expansions — `specs/epics/epic-07-multi-language-proof.md`
8. (new) Fix stale import examples in QUICK_REFERENCE + API docs — `specs/epics/epic-01-product-truth.md`
9. (new) Consolidated smoke-test suite — `specs/epics/epic-08-ci-hardening.md`
10. beckmt4/anime-subtitle-pipeline#24 — JAV domain pack v1

## Recently completed
- beckmt4/anime-subtitle-pipeline#85 — DB migration runner, completed in 04ad3c8
- beckmt4/anime-subtitle-pipeline#82, beckmt4/anime-subtitle-pipeline#86, beckmt4/anime-subtitle-pipeline#87, beckmt4/anime-subtitle-pipeline#83, beckmt4/anime-subtitle-pipeline#107, beckmt4/anime-subtitle-pipeline#89, and beckmt4/anime-subtitle-pipeline#110 — completed in 8bbd4f0
- beckmt4/anime-subtitle-pipeline#108 — legacy ASR-segment polish cleanup, completed in a999067
- beckmt4/anime-subtitle-pipeline#109, beckmt4/anime-subtitle-pipeline#111, and beckmt4/anime-subtitle-pipeline#112 — cleanup/docs work completed before this update
- beckmt4/anime-subtitle-pipeline#84 — MKV artifact registration acceptance coverage, completed in 7abbcf4
- beckmt4/anime-subtitle-pipeline#52 — explainable source-selection report acceptance mapping, completed in 7ceb66e
- beckmt4/anime-subtitle-pipeline#53 — generate inspect-only flow, completed in 8a40309
- beckmt4/anime-subtitle-pipeline#80 — ASR quality diagnostics and warning propagation, completed in e1f4304
- beckmt4/anime-subtitle-pipeline#75 — translation engine selector and hybrid routing, completed in e052084
- Runtime cleanup and core module wrappers — completed in b05155e and f0da0d2
- beckmt4/anime-subtitle-pipeline#54 — candidate confidence scoring, ASR warning-density review routing, and SRT overlap prevention, completed in dc8f59d
- beckmt4/anime-subtitle-pipeline#19 — generate-mode hardening epic, closed after #52, #53, #54, and #80 completion
- beckmt4/anime-subtitle-pipeline#74 — direct context-aware LLM translation engine (LLMDirectTranslator)
- beckmt4/anime-subtitle-pipeline#76 — literal-first / natural-subtitle second-pass workflow with drift guard
- beckmt4/anime-subtitle-pipeline#77 — live-action and adult-dialogue translation profile
- beckmt4/anime-subtitle-pipeline#79 — translation QC judge (deterministic checks; LLM judge optional)
- beckmt4/anime-subtitle-pipeline#81 — local model and hardware evaluation matrix (framework + docs)
- beckmt4/anime-subtitle-pipeline#56 — review-task generation rules (generate + benchmark routing)
- beckmt4/anime-subtitle-pipeline#55 — language-pack routing hooks in orchestrator
- beckmt4/anime-subtitle-pipeline#26 — language-pack architecture for multi-language expansion
- Epic product truth reset — FILE_OVERVIEW.md, PROJECT_SUMMARY.md, product-readiness.md, architecture guard tests, acceptance-test index

## Definition of done
A milestone is done only when:
- code is merged
- tests pass
- acceptance criteria pass
- docs are updated
- benchmark or validation artifacts exist where applicable
- generated outputs include enough metadata to explain what happened and why
