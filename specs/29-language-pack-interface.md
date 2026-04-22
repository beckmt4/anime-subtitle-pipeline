# Spec — Issue #29: Define language pack interface

**Issue:** #29  
**Status:** implemented  
**Parent:** #15 — Subtitle Intelligence Platform master tracker

---

## Problem

The platform currently hardcodes Japanese-specific assumptions throughout
`core` modules:

- `orchestrator._LANG_ALIASES` embeds `ja`/`en` alias sets directly.
- `llm_polish._CJK_RE` and `_recover_leading_english` are Japanese-output
  artefacts from qwen2.5:7b that have no place in a generic polish module.
- `mt.translate_candidate_jp_to_en` encodes the translation direction in its
  name.
- `media_inspect.LANG_MAP` contains Japanese-specific variants without a clear
  ownership boundary.

There is no stable contract that says *"this is what a language pack must
supply"*.  Adding Chinese→English or Spanish→English support today would
require editing core modules.

## Scope

**In scope:**
- Define the data contract for a language pack.
- Create the `packs/language/ja_en/` reference implementation.
- Document injection points (where core modules accept pack parameters).
- Write acceptance criteria (`acceptance/29-language-pack-interface.md`).

**Out of scope:**
- Moving capability code from root files to `core/` (Phase 2/3 migration).
- Adding a second language pack (that validates the interface works).
- Config schema changes to select the active language pack.

---

## Design

### What a language pack must supply

A language pack is a Python sub-package under `packs/language/<src>_<tgt>/`
that exposes the following:

| Symbol | Type | Purpose |
|---|---|---|
| `SOURCE_LANG` | `str` | ISO-639-1 source language code |
| `TARGET_LANG` | `str` | ISO-639-1 target language code |
| `PACK_ID` | `str` | Canonical `"<src>_<tgt>"` identifier |
| `aliases.LANG_ALIASES` | `dict[str, frozenset[str]]` | Container tag → canonical code map |
| `aliases.normalise(tag)` | `str → str` | Normalise a raw container tag |
| `prompts.get_system_prompt(style)` | `str` | LLM system prompt for polish step |
| `prompts.get_user_prompt(text)` | `str` | Per-segment user prompt |
| `cjk_filter` *(optional)* | module | Post-processor hook for output artefacts |

### Injection points

Language pack configuration is injected at the following core module
boundaries:

| Core module | Parameter | Pack contribution |
|---|---|---|
| `core.media` / `choose_audio_track` | `lang_aliases` dict | `aliases.LANG_ALIASES` |
| `core.mt` / `MTBackend.translate` | `source_lang`, `target_lang` | `SOURCE_LANG`, `TARGET_LANG` |
| `core.polish` / `PolishBackend.polish` | `style_config` | `prompts.get_system_prompt()` |
| `core.polish` (post-processor) | callable hook | `cjk_filter.filter_candidate_cjk` |

### Reference implementation: `packs/language/ja_en/`

The `ja_en` pack is the reference implementation:

```
packs/language/ja_en/
├── __init__.py       SOURCE_LANG, TARGET_LANG, PACK_ID
├── aliases.py        JA_ALIASES, EN_ALIASES, LANG_ALIASES, normalise()
├── prompts.py        get_system_prompt(), get_user_prompt()
└── cjk_filter.py     has_cjk_leak(), recover_leading_english(),
                      filter_candidate_cjk()
```

---

## Acceptance criteria

See `acceptance/29-language-pack-interface.md`.

---

## Open questions

- Should language packs also supply model name defaults (e.g.,
  `PREFERRED_ASR_MODEL`, `PREFERRED_MT_MODEL`)? Deferred to Phase 3 when
  backend selection is refactored.
- Should the pack interface be formalised as an abstract base class or
  Protocol? The current approach is duck-typed; formalisation can happen
  alongside Phase 3.
