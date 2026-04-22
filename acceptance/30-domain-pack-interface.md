# Acceptance criteria — Issue #30: Define domain pack interface

**Issue:** #30  
**Status:** met

---

## Criteria

- [x] `packs/domain/anime/` package exists and is importable.
- [x] `packs/domain/anime/__init__.py` exposes `DOMAIN_ID = "anime"`.
- [x] `packs/domain/anime/style.py` defines `get_style_config()`.
      Returned dict contains required keys: `max_chars_per_line`,
      `max_lines_per_segment`, `llm_style`.
- [x] `packs/domain/jav/` package exists and is importable.
- [x] `packs/domain/jav/__init__.py` exposes `DOMAIN_ID = "jav"` and
      `REQUIRES_OPT_IN = True`.
- [x] `packs/domain/jav/privacy.py` defines `ContentGateError`,
      `assert_opt_in()`, `redact_metadata()`.
      `assert_opt_in(False)` raises `ContentGateError`.
      `assert_opt_in(True)` does not raise.
      `redact_metadata({"file": "/path/to/x.mp4"})["file"]` → `"<redacted>"`.
- [x] Spec `specs/30-domain-pack-interface.md` exists and documents injection
      points and style config contract.
- [x] Domain-specific logic (honorifics, privacy gates) is NOT present in any
      `core/` module — it lives only in `packs/domain/`.

---

## Test evidence

Unit tests covering the domain packs are in
`tests/test_packs_domain.py`.

Tests run and pass with `pytest tests/test_packs_domain.py`.

---

## Notes

- The anime glossary (`glossary.yaml`) is not yet populated; that is content
  work tracked in Issue #23.
- Full JAV privacy audit (all sensitive key enumeration) is deferred to
  Issue #24.
- The `REQUIRES_OPT_IN` check is defined in `packs/domain/jav/privacy.py` and
  must be enforced by `core.runtime` at pipeline startup (Phase 4).
