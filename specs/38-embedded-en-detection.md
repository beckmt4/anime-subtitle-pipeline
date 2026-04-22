# Spec — Issue #38: Fix embedded English subtitle detection in generate mode

**Issue:** #38
**Status:** implemented

---

## Problem

`run_generate()` is supposed to prefer embedded English text subtitles over any
generation path (ASR → MT → LLM). In practice, some files with valid English
subtitle tracks were silently falling through to machine-generated output because
the source-selection code did not recognise all real-world language tag variants.

Two confirmed failure patterns:

1. **A Couple of Cuckoos S01E01** — English subtitle track tagged `eng` (ISO 639-2)
   was not selected; pipeline fell through to JP audio → ASR → MT.

2. **Once Upon a Crime (2023)** — English subtitle track tagged `en-US` (BCP-47
   regional subtag) was not selected; same fallback path.

---

## Scope

**In scope:**
- Fix `_lang_matches` in `orchestrator.py` to handle BCP-47 regional subtags
- Extend `LANG_MAP` in `media_inspect.py` with full language name aliases
- Add per-stream logging in `_first_text_sub` and `_first_audio_order`
- Add regression fixtures and tests for both failure patterns
- Add acceptance doc

**Out of scope:**
- Sidecar SRT file discovery (pipeline only uses streams from the container)
- Changing the priority order of the strategy decision tree
- Title-field-based language inference (no confirmed failures for this case)

---

## Design

### Root cause: `_lang_matches` missing BCP-47 handling

`_LANG_ALIASES["en"]` contained `{"en", "eng", "en-us", "en-gb"}` — an
incomplete explicit list. Any code not in this set (e.g. `en-AU`, `en-CA`,
`en-US` if case-changed) would return `False`, causing `_first_text_sub` to
return `None` for a valid English subtitle stream.

### Fix 1 — BCP-47 prefix matching in `_lang_matches`

```python
def _lang_matches(stream_lang: str | None, target: str) -> bool:
    if not stream_lang:
        return False
    code = stream_lang.strip().lower()
    aliases = _LANG_ALIASES.get(target, {target})
    if code in aliases:
        return True
    # BCP-47 prefix: 'en-AU' → prefix 'en', check if prefix is a known alias.
    prefix = code.split("-", 1)[0]
    return prefix in aliases
```

This covers all `en-*` variants (and `ja-*` variants) without an exhaustive list.

### Fix 2 — Full language name aliases in `LANG_MAP`

Add `"english"` → `"en"`, `"japanese"` → `"ja"`, `"french"` → `"fr"`,
`"chinese"` → `"zh"` to `LANG_MAP` in `media_inspect.py`. Some muxers (e.g.
older Handbrake presets, certain remux tools) write the full name as the
language tag value.

After normalization, `s.language` will be `"en"` instead of `"english"`, so
existing `_lang_matches` logic (and the explicit aliases) works correctly.

### Fix 3 — Per-stream acceptance/rejection logging

Add `logger.info` on ACCEPT and `logger.debug` on REJECT in `_first_text_sub`
and `_first_audio_order`. This lets operators see exactly why a track was
chosen or skipped without needing to attach a debugger.

Example log output:
```
  subtitle stream 1 (codec=pgssub lang=jpn): skipped — bitmap/image-based track
  subtitle stream 2 (codec=subrip lang=eng): ACCEPTED as en text subtitle
```

### Regression fixtures

| File | Scenario |
|---|---|
| `fixtures/ffprobe/couple_of_cuckoos_s01e01.json` | JA audio, bitmap JA sub (index 1), text EN sub tagged `eng` (index 2) |
| `fixtures/ffprobe/once_upon_a_crime.json` | JA audio, bitmap JA sub (index 1), text JA sub (index 2), text EN sub tagged `en-US` (index 3) |

---

## Acceptance criteria

See `acceptance/38-embedded-en-detection.md`.

---

## Open questions at implementation time

- **Are there other unrecognised tag forms in the wild?** Possibly (e.g.
  `"English (SDH)"` in the title field used as a language code). Not adding
  fuzzy title matching now — no confirmed failures for this pattern, and it
  risks false positives. Log output will expose future cases.

---

## Notes

- No change to the strategy decision tree was needed — the preference order
  (`embedded_en` > `en_audio_asr` > `embedded_jp_mt` > `ja_audio_asr_mt`) was
  already correct. Only the language detection was broken.
- `skip_embedded_en` flag behavior is unchanged and covered by a new test.
