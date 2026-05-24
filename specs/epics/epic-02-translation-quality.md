# Epic 02 — Translation quality productization (remaining tasks)

**Status:** Mostly complete. LLM-direct (#74), two-pass (#76), live-action
profile (#77), and translation QC judge (#79) are all implemented and tested.
Remaining gaps are listed below.

**Parent:** beckmt4/anime-subtitle-pipeline#73 (translation quality epic)

**Backlog reference:** `docs/BACKLOG.md` Phase 2, items 22 and 25

---

## Remaining tasks

### Task 02-A — Generalize LLMDirectTranslator prompts (`core/mt/__init__.py`)

**What:** `LLMDirectTranslator._build_prompt()` in `core/mt/__init__.py` contains
hardcoded language assumptions that should come from the active language pack:

1. Line ~642: `"You are translating Japanese dialogue into English subtitles.\n"` —
   hardcodes source and target language in the system prompt.
2. `target_lang="en"` in translation-memory lookup (line ~629) — hardcodes target.
3. `meta["source_text_ja"]` key — hardcodes "ja" in the key name; should be
   `source_text_<source_lang>` or language-agnostic `source_text`.

**Acceptance criteria:**
- [ ] `LLMDirectTranslator._build_prompt()` uses language-pack `get_system_prompt()`
      and `get_user_prompt()` hooks rather than hardcoded Japanese/English strings
- [ ] `target_lang` in memory lookup is supplied from the caller / pack, not hardcoded `"en"`
- [ ] Segment meta key for source text is language-agnostic (e.g. `source_text`)
      or uses the actual source language code
- [ ] `HybridTranslator` and `translate_candidate()` pass source/target language
      from the active pack to the LLM translator
- [ ] Existing translation engine selector tests still pass
- [ ] At least one test verifies that a non-Japanese pack hook could supply a
      different prompt without code changes

**Suggested implementation:**
- Accept `source_lang: str` and `target_lang: str` parameters in `_build_prompt()`
- Load prompt from `packs.language.load_pack(source_lang, target_lang).get_system_prompt()`
- Fall back to a generic "Translate {source_lang} dialogue into {target_lang} subtitles"
  if no pack is loaded

---

### Task 02-B — Translation benchmark corpus and model comparison reports (#78)

**What:** No fixture dataset exists for validating translation quality across
engines (Marian, LLM-direct, hybrid, two-pass). Without this, translation-quality
claims cannot be verified in CI.

**Acceptance criteria:**
- [ ] At least 20 text-only fixture cases exist in `fixtures/translation_benchmark/`
- [ ] Categories covered:
  - simple anime dialogue
  - honorific-heavy dialogue
  - signs / on-screen text
  - noisy ASR-derived dialogue (compression artifacts, low-confidence segments)
  - register-sensitive dialogue
  - ambiguous pronoun / relationship dialogue
- [ ] Each fixture has: source text, expected output (or acceptable range), category label
- [ ] `pytest` can run the corpus with mocked model outputs and produce a comparison
      table (engine vs. QC findings) without real model downloads
- [ ] A `docs/model-benchmark-procedure.md` documents the real local benchmark
      procedure for 4090-class machines

**No copyrighted media or subtitle text may be used in fixtures.**

---

### Task 02-C — Two-pass production safety validation

**What:** The two-pass workflow is implemented and tested but not yet validated
against realistic input. The drift guard and stock-phrase collapse guard need
stress-testing with the benchmark corpus fixtures.

**Acceptance criteria:**
- [ ] Benchmark corpus (from Task 02-B) covers at least 5 cases where literal pass
      and natural pass would produce measurably different outputs
- [ ] Drift guard catches at least 2 representative regression cases in corpus tests
- [ ] Stock-phrase collapse guard catches at least 1 representative case
- [ ] `docs/two-pass-translation-workflow.md` notes the known risk cases
