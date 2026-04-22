# Spec — Issue #30: Define domain pack interface

**Issue:** #30  
**Status:** implemented  
**Parent:** #15 — Subtitle Intelligence Platform master tracker

---

## Problem

The platform currently has no mechanism to inject domain-specific behaviour.
Adding anime vs. JAV vs. film support today would require editing core modules
directly, creating coupling that makes every new domain a special case.

There is no stable contract that says *"this is what a domain pack must
supply"*.  Anime-specific honorific rules, JAV-specific privacy controls, and
documentary-specific formatting choices all belong in domain packs, not in
`core`.

## Scope

**In scope:**
- Define the data contract for a domain pack.
- Create stub implementations for `packs/domain/anime/` and `packs/domain/jav/`.
- Document injection points (where core modules accept domain pack parameters).
- Write acceptance criteria (`acceptance/30-domain-pack-interface.md`).

**Out of scope:**
- Full anime glossary population (that is content work for Issue #23).
- Full JAV privacy audit (that is policy work for Issue #24).
- Config schema changes to select the active domain pack (Phase 3/4).

---

## Design

### What a domain pack must supply

A domain pack is a Python sub-package under `packs/domain/<domain_id>/`
that exposes the following:

| Symbol | Type | Purpose |
|---|---|---|
| `DOMAIN_ID` | `str` | Canonical domain identifier |
| `REQUIRES_OPT_IN` | `bool` | Whether explicit user opt-in is required |
| `style.get_style_config()` | `dict` | Style parameters for polish + formatting |

For restricted domains (e.g. JAV) an additional requirement applies:

| Symbol | Type | Purpose |
|---|---|---|
| `privacy.assert_opt_in(opt_in)` | `None` | Raise `ContentGateError` if not opted-in |
| `privacy.redact_metadata(meta)` | `dict` | Return privacy-safe copy of metadata |

### Style config contract

The dict returned by `get_style_config()` is passed to:
- `core.polish.PolishBackend.polish(candidate, style_config=…)`
- `core.subtitles` formatting utilities (line length, segment constraints).

Required keys:

| Key | Type | Description |
|---|---|---|
| `max_chars_per_line` | `int` | Maximum characters per subtitle line |
| `max_lines_per_segment` | `int` | Maximum lines per subtitle segment |
| `llm_style` | `str` | LLM style profile name (`"natural"` or `"literal"`) |

Optional domain-specific keys (examples):

| Key | Domain | Description |
|---|---|---|
| `preserve_honorifics` | anime | Keep Japanese honorifics in EN output |
| `honorific_list` | anime | List of honorific strings to preserve |
| `skip_op_ed_segments` | anime | Don't polish OP/ED lyric segments |
| `translate_on_screen_text` | anime | Include translated sign cues |

### Injection points

| Core module | Parameter | Domain pack contribution |
|---|---|---|
| `core.polish` / `PolishBackend.polish` | `style_config` | `style.get_style_config()` |
| `core.subtitles` (formatting) | line length / constraint params | `style_config["max_chars_per_line"]` |
| `core.runtime` (startup) | opt-in gate | `privacy.assert_opt_in(opt_in)` |
| `core.artifacts` (storage) | metadata sanitisation | `privacy.redact_metadata(meta)` |

### Reference implementations

**`packs/domain/anime/`** (content-safe, no opt-in required):
```
packs/domain/anime/
├── __init__.py   DOMAIN_ID = "anime"
└── style.py      get_style_config()
```

**`packs/domain/jav/`** (adult content, opt-in required):
```
packs/domain/jav/
├── __init__.py   DOMAIN_ID = "jav", REQUIRES_OPT_IN = True
└── privacy.py    ContentGateError, assert_opt_in(), redact_metadata()
```

---

## Acceptance criteria

See `acceptance/30-domain-pack-interface.md`.

---

## Open questions

- Should domain packs supply benchmark fixture references (e.g., path to
  reference SRT for anime-specific benchmark runs)? Deferred to Issue #23/#24.
- Should the pack interface be formalised as a Protocol? Deferred alongside
  language pack formalisation.
- Glossary support (`glossary.yaml`) for anime pack: YAML schema not yet
  defined. Tracked as a sub-task of Issue #23.
