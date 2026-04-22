# ADR-002: Anime + JAV Pack Model

**Status:** Accepted  
**Issue:** #32  
**Date:** 2026-04-22  
**Deciders:** Platform team  
**Parent roadmap:** #15 — Subtitle Intelligence Platform master tracker

---

## Context

The platform needs to support at least two content domains with meaningfully
different requirements:

1. **Anime** — Animated series and films.  Key requirements: preserve Japanese
   honorifics, handle OP/ED sequences gracefully, translate on-screen signs,
   apply natural-English polish style.

2. **JAV (Japanese Adult Video)** — Adult content domain.  Key requirements:
   explicit user opt-in before any processing, logging redaction (no file
   paths or metadata in logs/artifacts), content gate enforcement.

These two domains share the same underlying pipeline (ASR → MT → polish →
SRT) but differ in style policy, privacy requirements, and safety gates.
Hardcoding both into `core` would create tangled conditional logic.

This ADR decides how anime and JAV are modelled as domain packs and what
boundary separates their configuration from core platform code.

---

## Decision

### 1. Both domains are implemented as `packs/domain/<id>/` packages

Anime and JAV are peer domain packs, not special cases in core.  Core modules
never switch on domain names; they accept domain configuration as injectable
parameters.

```
packs/domain/
├── anime/
│   ├── __init__.py    DOMAIN_ID = "anime"
│   └── style.py       get_style_config()
└── jav/
    ├── __init__.py    DOMAIN_ID = "jav", REQUIRES_OPT_IN = True
    └── privacy.py     assert_opt_in(), redact_metadata(), ContentGateError
```

### 2. Domain packs supply a style config dict

The primary contract between a domain pack and `core` is the style config
dict returned by `style.get_style_config()`.  This dict is passed as a
parameter to `core.polish.PolishBackend.polish()` and to `core.subtitles`
formatting utilities.

Required keys in any domain style config:

| Key | Type | Notes |
|---|---|---|
| `max_chars_per_line` | int | Subtitle line character limit |
| `max_lines_per_segment` | int | Max lines per segment |
| `llm_style` | str | LLM style profile (``"natural"`` / ``"literal"``) |

Domain packs may add additional keys that are consumed by their own
post-processor hooks.

### 3. Anime domain — style-only pack

The anime pack supplies style parameters and a glossary.  It has no privacy
or content gate requirements (`REQUIRES_OPT_IN = False` by default).

Anime-specific style parameters:

| Parameter | Value | Rationale |
|---|---|---|
| `preserve_honorifics` | `True` | Target audience expects Japanese honorifics |
| `skip_op_ed_segments` | `True` | OP/ED lyrics are not subtitle content |
| `translate_on_screen_text` | `True` | Signs provide plot-relevant context |
| `llm_style` | `"natural"` | Entertainment content benefits from natural EN |

The anime glossary (`glossary.yaml`) will be populated in Issue #23.

### 4. JAV domain — privacy-first pack

The JAV pack imposes additional requirements beyond style:

**Content gate:** `packs.domain.jav.privacy.assert_opt_in(opt_in)` must be
called by `core.runtime` at pipeline startup.  It raises `ContentGateError`
if the `adult_content_opt_in` config flag is not explicitly set to `True`.

**Logging redaction:** `packs.domain.jav.privacy.redact_metadata(meta)` must
be applied before any metadata dict is written to logs, artifacts, or
benchmark output.  Sensitive keys (`file`, `file_path`, `video_path`, etc.)
are replaced with `"<redacted>"`.

**Why a content gate:**
- Prevents accidental processing of adult content on shared machines.
- Provides a clear audit trail that consent was given.
- Satisfies basic due-diligence requirements for adult content workflows.

### 5. Domain selection is a runtime configuration concern

The active domain pack is selected in `config.yaml`:

```yaml
domain:
  pack: anime          # "anime" | "jav" | null (no domain pack)
  adult_content_opt_in: false   # must be true when pack is "jav"
```

`core.runtime` reads this config and loads the appropriate pack module.  Core
capability modules (`core.mt`, `core.polish`, etc.) never read the domain
config directly; they receive the domain's parameters as function arguments.

---

## Alternatives Considered

### A. Single domain with feature flags

Use a single `domain_config` dict with boolean flags (`honorifics: true`,
`adult_mode: true`).

**Rejected:** Feature flags accumulate over time and create combinatorial
complexity.  The pack model makes each domain's requirements explicit and
isolated.

### B. Separate top-level packages (`anime_pack/`, `jav_pack/`)

Structure domains as independent top-level packages rather than sub-packages
of `packs/domain/`.

**Rejected:** Inconsistent with the platform's unified directory contract.
All packs live under `packs/` for discoverability and consistent import paths.

### C. Inherit from a `DomainPack` abstract base class

Formalise the domain pack interface as an ABC or Protocol.

**Deferred:** Duck-typing with documented conventions is sufficient for Phase 1.
A formal Protocol can be added once a third domain pack is needed, which will
validate that the interface is truly stable.

---

## Consequences

**Positive:**
- Anime and JAV behaviours are isolated; a bug in JAV privacy code cannot
  accidentally affect anime processing.
- Adding a new domain (e.g., film, documentary) follows the same pattern
  without touching `core`.
- The content gate for JAV is enforced at a single, auditable entry point.

**Negative / trade-offs:**
- Two domain packs shipped initially means the interface is validated against
  only two concrete cases.  Edge cases may emerge when a third domain is added.
- The glossary for anime (`glossary.yaml`) is stubbed; it must be populated
  before the anime pack provides meaningful quality improvement (Issue #23).
- Full JAV metadata key enumeration is deferred to Issue #24; the current
  `_REDACTED_KEYS` set is a starting point, not a complete audit.

---

## Growth Path: Multi-Language + Additional Domains

The pack model is designed to scale to:

| Future addition | How it fits |
|---|---|
| Chinese→English | Add `packs/language/zh_en/` following the `ja_en` reference |
| Spanish→English | Add `packs/language/es_en/` |
| Korean Drama domain | Add `packs/domain/kdrama/` with its own style config |
| Documentary domain | Add `packs/domain/documentary/` with literal style default |
| Multi-language output | `core.mt` accepts target_lang parameter; language pack supplies target |

No core module changes are required for any of these additions.  The
`core.runtime` config reader must be extended to map new pack IDs to their
module paths, but that is a small, localised change.

---

## References

- `docs/architecture/module-boundaries.md` — module ownership map.
- `docs/architecture/adr-001-local-first-platform.md` — platform-level
  architecture decisions.
- `specs/30-domain-pack-interface.md` — domain pack data contract.
- `packs/domain/anime/` — anime reference implementation.
- `packs/domain/jav/` — JAV reference implementation.
