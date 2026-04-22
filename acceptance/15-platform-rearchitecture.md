# Acceptance criteria — EPIC #15 / Issue #: Re-architect into subtitle intelligence platform

**Issue:** #15 (EPIC) / child of master tracker  
**Status:** phase-1-met

---

## Criteria

### Architecture documentation

- [x] Architecture doc exists at `docs/architecture/module-boundaries.md`.
- [x] ADR-001 (local-first platform) exists at
      `docs/architecture/adr-001-local-first-platform.md`.
- [x] ADR-002 (anime + JAV pack model) exists at
      `docs/architecture/adr-002-pack-model.md`.

### Core platform modules defined

- [x] `core/` package skeleton created with `__init__.py` for all 12 modules:
      `media`, `extract`, `ocr`, `asr`, `mt`, `polish`, `subtitles`,
      `benchmark`, `artifacts`, `policy`, `review`, `runtime`.
- [x] Abstract base interfaces defined for pluggable backends:
      `ASRBackend` (`core/asr`), `MTBackend` (`core/mt`),
      `PolishBackend` (`core/polish`), `OCRBackend` (`core/ocr`).
- [x] Core → root shims in place so existing tests continue to pass.

### Language pack interface defined

- [x] Spec `specs/29-language-pack-interface.md` exists.
- [x] `packs/language/ja_en/` reference implementation created.
- [x] Acceptance criteria `acceptance/29-language-pack-interface.md` exist.
- [x] Tests `tests/test_packs_language_ja_en.py` pass.

### Domain pack interface defined

- [x] Spec `specs/30-domain-pack-interface.md` exists.
- [x] `packs/domain/anime/` reference implementation created.
- [x] `packs/domain/jav/` reference implementation created.
- [x] Acceptance criteria `acceptance/30-domain-pack-interface.md` exist.
- [x] Tests `tests/test_packs_domain.py` pass.

### Target repo structure documented

- [x] Target directory tree documented in
      `docs/architecture/module-boundaries.md` Section 8.
- [x] Current file → target module mapping documented in Section 9.

### Growth path explicit

- [x] Multi-language growth path documented in ADR-002 (Growth Path section).
- [x] Anime and JAV extension paths documented in ADR-002 and
      `docs/architecture/module-boundaries.md`.

---

## Test evidence

```
pytest tests/test_packs_language_ja_en.py tests/test_packs_domain.py -v
```

All tests pass.

---

## Notes

- Japanese-specific logic (`_LANG_ALIASES`, `_CJK_RE`) has been extracted from
  the core design into `packs/language/ja_en/`.  The root-level `orchestrator.py`
  still contains `_LANG_ALIASES` pending Phase 3 migration; the pack now holds
  the canonical copy.
- Phase 2–5 migration (moving root files into `core/`) is tracked separately
  and is not required for this EPIC's acceptance criteria.
