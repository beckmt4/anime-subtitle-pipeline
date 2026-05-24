# Epic 07 — Multi-language platform proof

**Status:** Language-pack architecture is implemented and the ja_en reference
pack is fully functional. Pack structure exists for en_en, ko_en, zh_en, es_en.
However, core modules still contain hardcoded Japanese/English assumptions, and
no non-Japanese workflow has been proven end-to-end in tests.

**Parent:** beckmt4/anime-subtitle-pipeline#27

**Backlog reference:** `docs/BACKLOG.md` Phase 7, item 36

---

## Tasks

### Task 07-A — en_en transcription-only pack

**What:** English audio → English subtitles via ASR, with no MT step. This is
the simplest non-Japanese workflow and proves that the platform can handle
transcription-only paths.

**Why en_en first:** Low risk (no MT required), immediately useful for English
media, and validates the language-pack routing hook with a degenerate MT case.

**Acceptance criteria:**
- [ ] `packs/language/en_en/` has complete routing that skips MT when
      `source_lang == target_lang`
- [ ] `run_generate()` with an English audio source and `en_en` pack active
      produces an SRT from ASR alone
- [ ] `packs/language/en_en/prompts.py` has a prompt for optional LLM transcript
      cleanup (grammar/punctuation polish, not translation)
- [ ] End-to-end test (mocked ASR) proves en_en path runs without MT call
- [ ] Source-selection report notes "transcription-only" when en_en is active

---

### Task 07-B — Add one second real translation pack (ko_en or zh_en)

**What:** Prove that the language-pack architecture works for a second source
language. Recommended: `ko_en` (Korean → English) as it is structurally similar
to ja_en.

**Why a real second pack matters:**
The en_en pack avoids MT, so it does not prove MT direction is language-agnostic.
A ko_en pack that calls a real (or mocked) MT model proves the routing is truly
language-agnostic.

**Acceptance criteria:**
- [ ] `packs/language/ko_en/` has complete routing hooks, aliases, and prompts
- [ ] `packs/language/ko_en/prompts.py` defines a Korean-specific system prompt
      (do not copy-paste ja_en Japanese-specific prompt)
- [ ] MT model selection for ko_en documented in `config.yaml` comments
      (e.g. `Helsinki-NLP/opus-mt-ko-en` as the Marian baseline)
- [ ] End-to-end test (mocked MT) proves ko_en path produces a `SubtitleCandidate`
      with `source_lang=ko` metadata
- [ ] `packs/language/__init__.py` `list_available_packs()` returns `ko_en`
- [ ] Docs updated to state which packs are real (ja_en, ko_en) vs. planned
      (zh_en, es_en)

---

### Task 07-C — Remove hardcoded ja/en assumptions from core modules

**What:** Several residual hardcoded assumptions remain in core after the
language-pack migration. These must be removed before the platform can
claim to be language-agnostic.

**Known locations:**
- `core/mt/__init__.py` line ~642: `"You are translating Japanese dialogue into English subtitles."` (also tracked in Epic 02 Task A)
- `core/mt/__init__.py` line ~476: `meta={"source_text_ja": s.text, ...}` — key encodes language
- `core/mt/__init__.py` line ~737: same `source_text_ja` key
- `core/review/workflow.py` line ~335: `meta.get("source_text_ja", "")` — reads hardcoded key
- `core/polish/__init__.py` lines ~272, ~281, ~304, ~432, ~458: `text_ja` parameter names and prompt text

**Acceptance criteria:**
- [ ] No `source_text_ja` hardcoded key in any `core/` module; use `source_text`
      or `source_text_{lang}` with the actual source language code
- [ ] No `text_ja` parameter in `core/polish/__init__.py` public API; rename to
      `source_text` with `source_lang` parameter
- [ ] No hardcoded "Japanese dialogue into English subtitles" in any `core/` module
      (also satisfies Epic 02 Task A)
- [ ] `core/review/workflow.py` reads source text using a language-agnostic key
- [ ] `tests/test_architecture_guard.py` guard `test_no_hardcoded_ja_en_in_core_mt`
      passes after these changes
- [ ] All existing tests still pass after the rename

---

### Task 07-D — Language-specific QC hooks

**What:** Some QC checks are language-specific but currently live in generic modules.

**Known cases:**
- CJK leakage check in `translation_qc.py` — this is a Japanese-output quality
  quirk and should be a ja_en pack hook, not a generic check
- Target-language text validation (is the output actually in the target language?)
  should be a pack hook, not hardcoded

**Acceptance criteria:**
- [ ] CJK leakage check is moved to `packs/language/ja_en/` and called via a
      `validate_output(text, target_lang)` hook on the language pack
- [ ] Non-Japanese packs do not trigger CJK leakage warnings
- [ ] Target-language validation hook defined in the `LanguagePack` interface
- [ ] Tests verify: ja_en pack triggers CJK warning; en_en pack does not

---

### Task 07-E — Docs: which packs are real vs. planned

**What:** The README and docs currently list ko_en/zh_en/es_en as if they are
functional, when they are only structural stubs.

**Acceptance criteria:**
- [ ] `docs/FILE_OVERVIEW.md` `packs/` section updated to note which packs
      are production-ready vs. structure-only (already done for FILE_OVERVIEW;
      verify docs/README sections are also accurate)
- [ ] `packs/language/README.md` (or pack-level `__init__.py` docstrings) state
      per-pack readiness level
- [ ] No user-facing doc claims zh_en/es_en are usable without clarifying they
      need MT model configuration
