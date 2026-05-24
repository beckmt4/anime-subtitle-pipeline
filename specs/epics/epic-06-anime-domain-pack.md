# Epic 06 — Anime domain pack maturity (v1)

**Status:** Pack structure and interface exist (`packs/domain/anime/`,
`acceptance/30-domain-pack-interface.md`). Glossary/style YAML files are present
but content is thin. Honorific policy, signs/songs handling, and anime-specific
benchmark fixtures are all missing.

**Parent:** beckmt4/anime-subtitle-pipeline#23

**Backlog reference:** `docs/BACKLOG.md` Phase 5, item 31

---

## Tasks

### Task 06-A — Anime glossary and name fixtures

**What:** `packs/domain/anime/glossary.yml` exists but may be sparse. Populate
it with common anime-specific terms that should be preserved or translated
consistently, and add tests that verify injection into LLM prompts.

**Acceptance criteria:**
- [ ] `packs/domain/anime/glossary.yml` contains at least 20 representative entries
      covering honorifics, school/family terms, common anime tropes, and genre terms
- [ ] `packs/domain/anime/names.yml` contains guidance on name ordering
      (family-name-first vs. given-name-first) and romanization style
- [ ] `tests/test_packs_domain.py` verifies that glossary terms are injected into
      `LLMDirectTranslator` prompts when the anime domain pack is active
- [ ] Name preservation tested: a segment containing a name from `names.yml` should
      produce a QC warning if the name is absent from the output

---

### Task 06-B — Honorific policy

**What:** Honorific handling (san/kun/chan/senpai/sensei preservation vs. dropping)
is a key anime-style decision. Currently no explicit policy exists.

**Acceptance criteria:**
- [ ] `packs/domain/anime/style.yml` documents the default honorific policy
      (preserve vs. drop vs. anglicize)
- [ ] `config.yaml` has an `anime.honorifics` option to switch policy
- [ ] `LLMDirectTranslator` injects the active honorific policy into the system prompt
- [ ] Tests verify: honorific-preserve mode keeps `-san` in output;
      honorific-drop mode does not flag missing honorific as a QC error

---

### Task 06-C — Signs, songs, and OP/ED policy

**What:** Anime has several subtitle categories that need explicit handling
decisions: signs (on-screen text), OP/ED song lyrics, karaoke subtitles,
and forced subtitles.

**Acceptance criteria:**
- [ ] `packs/domain/anime/style.yml` documents the policy for each category:
  - Signs: translate, skip, or OCR?
  - OP/ED song lyrics: include (with or without romanization), skip, or stub?
  - Karaoke subtitles: include, skip, or convert to plain subtitle?
  - Forced subtitles: always include
- [ ] Metadata flags added to `SubtitleCandidate` for detected sign/song content
      (detection can be heuristic: all-caps, known OP/ED timing patterns, etc.)
- [ ] Policy documented in `docs/` or pack README

**Note:** No copyrighted song lyrics may be used in tests or fixtures.
Use synthetic or public-domain text.

---

### Task 06-D — Anime benchmark fixtures

**What:** Fixture text cases that exercise anime-specific QC and prompt behavior.

**Acceptance criteria:**
- [ ] At least 5 anime-specific fixture cases in `fixtures/translation_benchmark/anime/`:
  - Honorific-heavy dialogue (e.g. "Yamada-san, please help Tanaka-kun")
  - School/family relationship dialogue
  - Sign text (synthetic on-screen text)
  - OP/ED lyric-like text (no copyrighted lyrics; public domain or synthetic)
  - Ambiguous pronoun/relationship (ore/boku/watashi, senpai/kouhai)
- [ ] Fixtures integrated with the benchmark corpus runner (Task 02-B)
- [ ] Tests cover that anime pack fixtures run cleanly with mocked models

---

### Task 06-E — Anime source-selection tuning

**What:** The generate orchestrator prefers Japanese audio/subs for anime
but does not explain whether the preference is pack-driven or hardcoded.

**Acceptance criteria:**
- [ ] Anime pack exposes a `preferred_source_types` hint consumed by the orchestrator
- [ ] Source-selection report notes when anime pack preference influenced routing
- [ ] README explains how to enable anime mode and what it changes

---

## Related

- JAV domain pack v1 (beckmt4/anime-subtitle-pipeline#24) — tracked separately
  but shares the domain pack interface. JAV tasks:
  - Privacy-aware operation (no copyrighted material, real names flagged)
  - Adult register preservation (relies on live-action/adult profile — Epic 02 / #77)
  - Privacy rules for on-screen text (censor real names in output)
  - JAV-specific fixtures (synthetic only; no real JAV content)
