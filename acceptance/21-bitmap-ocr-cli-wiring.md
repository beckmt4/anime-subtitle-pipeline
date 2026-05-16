# Acceptance criteria — Issue #21: wire OCR backend into CLI generate/benchmark

**Issue:** #21  
**Status:** met

## Criteria

- [x] OCR config includes `ocr.enabled`, `ocr.backend`, `ocr.language_models`, `ocr.confidence_warn_below`.
- [x] OCR backend plugin entrypoint is available via `core.ocr.create_backend(cfg)`.
- [x] `main.py --mode generate` constructs configured OCR backend and passes it to `run_generate(...)`.
- [x] Generate `--inspect-only` uses the same OCR config path.
- [x] Benchmark mode includes bitmap EN OCR and bitmap JP OCR→MT candidates when OCR is enabled.
- [x] Benchmark/generate clearly skip bitmap OCR when backend is not configured.
- [x] Tests cover CLI generate OCR wiring and benchmark bitmap inclusion/exclusion behavior.
- [x] README documents OCR setup and plugin backend limitations.

## Parent epic mapping

- `beckmt4/anime-subtitle-pipeline#21`: bitmap subtitle OCR is now wired through standard CLI generate and benchmark paths (including inspect-only planning behavior).
