# Acceptance criteria — EPIC: Introduce language-pack architecture for multi-language expansion

**Issue:** #15 child — multi-language expansion  
**Status:** met

---

## Criteria

### Core product no longer assumes Japanese source

- [x] `FasterWhisperASR` class docstring and `transcribe_audio_to_segments` docstring
      no longer describe the class as "Japanese ASR"; both are now language-agnostic.
- [x] `core.asr.ASRBackend.transcribe` accepts a `language` hint as a parameter
      supplied by the caller; it does not default to Japanese internally.
- [x] `core.mt.MTBackend.translate` accepts `source_lang` and `target_lang` as
      explicit parameters; the translation direction is never hardcoded.
- [x] `core.polish.PolishBackend.polish` accepts a `style_config` dict from the
      active language/domain pack; it does not embed Japanese-specific style rules.
- [x] Japanese-specific logic (`_LANG_ALIASES`, `_CJK_RE`, CJK recovery) lives only
      in `packs/language/ja_en/` — not in any `core/` module.

### Language pack interface is implemented

- [x] `packs/language/ja_en/` package exists and is importable as the reference pack.
- [x] `packs/language/ja_en/__init__.py` exposes `SOURCE_LANG`, `TARGET_LANG`, `PACK_ID`.
- [x] `packs/language/ja_en/aliases.py` defines `LANG_ALIASES`, `normalise()`.
- [x] `packs/language/ja_en/prompts.py` defines `get_system_prompt()`, `get_user_prompt()`.
- [x] `packs/language/ja_en/cjk_filter.py` defines CJK leak detection and recovery.
- [x] `packs/language/ja_en/routing.py` defines `translate_candidate()` and
      `UNTAGGED_AUDIO_FALLBACK_SOURCE_LANGUAGE`.
- [x] `packs.language.LanguageRoutingHooks` dataclass formalises the routing contract.
- [x] Spec `specs/29-language-pack-interface.md` documents the full interface contract.

### Language pack registry

- [x] `packs.language.list_available_packs()` returns the pack IDs of all installed
      language packs, enabling runtime discovery without hardcoding pack names.
- [x] `packs.language.load_language_routing_hooks(source, target)` loads any
      installed pack by ISO-639-1 pair; raises `ValueError` for unknown pairs.
- [x] Adding a new language pack requires only creating the sub-package; no core
      code changes are needed to make it discoverable.

### ASR/MT/polish routing can vary by language

- [x] `orchestrator.run_generate` reads the active language pack from config
      (`packs.language` key) and loads routing hooks at startup.
- [x] Translation routing (`translate_candidate`) is delegated to the active pack;
      core orchestration never calls the ja→en workflow directly.
- [x] Untagged-audio fallback source-language policy is owned by the pack
      (`UNTAGGED_AUDIO_FALLBACK_SOURCE_LANGUAGE`), not hardcoded in core.
- [x] LLM polish prompt is loaded from the pack (`prompts.get_system_prompt()`).

### Multiple target languages supported in the design and persistence model

- [x] `core.subtitles.SubtitleCandidate.language` records the **output** language
      of a candidate (e.g. ``'en'`` for a translated subtitle track).
- [x] `core.artifacts.models.SubtitleCandidateRecord` now has an optional
      `source_language` field: the ISO 639-1 code of the language translated
      *from* for MT candidates (``'ja'`` when ``language='en'``), ``None`` for
      ASR and embedded candidates.
- [x] `subtitle_candidates` SQLite table has a `source_language` column (nullable).
      Existing databases are upgraded automatically via the migration in
      `docs/migrations/001_add_source_language_to_candidates.sql`.
- [x] `ArtifactRegistry.store_candidate` persists `source_language` alongside
      `language` so both the output language and the original source language
      are queryable.
- [x] `_reg_store_candidate` in orchestrator passes `source_language=translation_source_language`
      for all `source='mt'` and `source='mt_llm'` candidates, enabling per-direction
      reporting ("how many candidates were translated from Japanese vs. Chinese?").

---

## Test evidence

```bash
pytest tests/test_artifacts.py tests/test_packs_language_ja_en.py -v --tb=short
```

All tests pass.  Coverage includes:

- `SubtitleCandidateRecord` round-trips `source_language` through the registry.
- `list_available_packs()` returns `["ja_en"]` in the reference install.
- `load_language_routing_hooks("ja", "en")` returns a valid `LanguageRoutingHooks`.
- Unknown pack raises `ValueError`.

---

## Notes

- A second language pack (e.g. `zh_en`) would fully validate the interface is
  language-agnostic; adding one is straightforward — create
  `packs/language/zh_en/` following the `ja_en` reference implementation.
- Formal Protocol/ABC formalisation of the pack interface is deferred; the
  current duck-typed approach works and can be formalised alongside Phase 3
  backend-selection refactoring.
