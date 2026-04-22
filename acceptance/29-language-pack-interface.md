# Acceptance criteria — Issue #29: Define language pack interface

**Issue:** #29  
**Status:** met

---

## Criteria

- [x] `packs/language/ja_en/` package exists and is importable.
- [x] `packs/language/ja_en/__init__.py` exposes `SOURCE_LANG`, `TARGET_LANG`,
      `PACK_ID`.
- [x] `packs/language/ja_en/aliases.py` defines `LANG_ALIASES`, `normalise()`.
      `normalise("jpn")` → `"ja"`, `normalise("eng")` → `"en"`,
      `normalise("unknown")` → `"unknown"`.
- [x] `packs/language/ja_en/prompts.py` defines `get_system_prompt("natural")`,
      `get_system_prompt("literal")`, `get_user_prompt(text)`.
      Invalid style raises `ValueError`.
- [x] `packs/language/ja_en/cjk_filter.py` defines `has_cjk_leak()`,
      `recover_leading_english()`, `filter_candidate_cjk()`.
      `recover_leading_english("こんにちはHello")` → `"Hello"`.
- [x] Spec `specs/29-language-pack-interface.md` exists and documents injection
      points.
- [x] Core modules (`core.asr`, `core.mt`, `core.polish`) define abstract base
      interfaces that accept pack-supplied parameters.
- [x] Language-specific logic (`_LANG_ALIASES`, `_CJK_RE`, CJK recovery) is
      NOT present in any `core/` module — it lives only in `packs/`.

---

## Test evidence

Unit tests covering the `ja_en` pack are in
`tests/test_packs_language_ja_en.py`.

Tests run and pass with `pytest tests/test_packs_language_ja_en.py`.

---

## Notes

- The `packs/language/ja_en/` implementation is the reference pack.  A second
  language pack (e.g. `zh_en`) is not required to meet these criteria; it
  would validate that the interface is truly language-agnostic (tracked
  separately).
- Formal Protocol/ABC formalisation of the pack interface is deferred to Phase
  3 alongside backend selection refactoring.
