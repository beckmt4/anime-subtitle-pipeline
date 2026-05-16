# Two-Pass Translation Workflow

## Overview

The pipeline supports two translation workflows, selected via `translation.workflow` in `config.yaml`:

| Workflow | Key | When to use |
|---|---|---|
| Single-pass | `single_pass` | Standard anime with clean, unambiguous dialogue |
| Literal-then-natural | `literal_then_natural` | Live-action, JAV, or dialogue where accuracy matters most |

The default is `single_pass`, which matches the original pipeline behaviour.

---

## Single-pass (default)

```yaml
translation:
  workflow: single_pass
```

The pipeline runs one translation step followed by an optional LLM polish step:

```
Japanese source
  → Translation engine (Marian / LLM-direct / hybrid)
  → (Optional) LLM polish (natural or literal style)
  → Final subtitle
```

The polish step tries to solve accuracy, naturalness, and length constraints in a
single LLM call.  This works well for most anime where:

- Dialogue is relatively unambiguous.
- Subject-dropping is predictable from context.
- Content is suitable for a general-purpose subtitle style guide.

---

## Literal-then-natural two-pass

```yaml
translation:
  workflow: literal_then_natural
  save_intermediate: false   # set to true to store literal segments in metadata
```

The pipeline runs two sequential steps:

```
Japanese source
  Pass 1 → Translation engine (accuracy-first literal output)
  Pass 2 → LLM natural adaptation (readable subtitles, meaning locked to Pass 1)
  → Final subtitle
```

### Pass 1 — Literal translation

Pass 1 uses the configured translation engine (`translation.engine`) to produce a
literal English translation.  The goal is semantic accuracy:

- Preserve all nouns, names, and register.
- Retain sentence structure close to the Japanese source.
- Avoid any paraphrasing or naturalisation.

The literal candidate is stored in the final candidate's metadata under
`literal_pass_candidate_id`.  When `save_intermediate: true`, the literal segment
texts are also stored in `literal_pass_segments` for debugging.

### Pass 2 — Natural adaptation

Pass 2 feeds the literal translation **and** the Japanese source text to the LLM
with the `natural_from_literal` prompt style.  The LLM is instructed to:

1. Keep the exact meaning from the literal translation.
2. Produce natural, conversational subtitle English.
3. Preserve all names, honorifics, and cultural terms.

### Drift guard (QC safety)

Each segment in Pass 2 is checked against the literal output using the same drift
detection used in single-pass polish:

- If the natural output **drops a proper noun** or **significantly compresses** the
  literal text, the segment reverts to the literal translation.
- The reverted segment receives a `two_pass_qc_warning` meta key (value:
  `drift_reverted_to_literal:<reason>`) so review tooling can surface it.

A **stock-phrase collapse guard** also applies: if the LLM collapses all segments
into the same generic filler phrase (e.g., "Sure thing."), the entire batch reverts
to the literal pass and the candidate meta records
`two_pass_qc_warning: stock_phrase_collapse_reverted_to_literal`.

If the LLM is disabled or unreachable, Pass 2 falls back to the literal text with
`fallback: true` in the candidate meta.

---

## When to choose each workflow

### Use `single_pass` when

- The source is standard anime with predictable dialogue.
- You want the fastest pipeline with fewest LLM calls.
- Subtitle accuracy is good enough with a single polish step.

### Use `literal_then_natural` when

- The source is live-action or JAV content with ambiguous or blunt dialogue.
- You need an auditable trail showing what the literal translation said before any
  naturalisation took place.
- You have experienced hallucination or softening from a single-pass polish prompt.
- You want to compare the literal output against the final subtitle for QC.

---

## Configuration reference

```yaml
translation:
  workflow: single_pass        # single_pass | literal_then_natural
  save_intermediate: false     # save literal-pass segment texts in candidate metadata

  # Engine for Pass 1 (same as single-pass engine selector)
  engine: "marian"             # marian | llm_direct | hybrid
  fallback_engine: "marian"
  mode: "accuracy_first"       # literal | natural_subtitle | accuracy_first
  dialogue_profile: "default"  # default | live_action_adult

llm:
  enabled: true
  # Pass 2 uses the natural_from_literal prompt style (built-in).
  # The style key below applies to single-pass polish only.
  style: "natural"
```

---

## Candidate metadata produced

| Key | Location | Description |
|---|---|---|
| `translation_workflow` | candidate `meta` | `"literal_then_natural"` |
| `translation_pass` | literal candidate `meta` | `"literal"` |
| `literal_pass_candidate_id` | final candidate `meta` | ID of the literal-pass candidate |
| `literal_pass_segments` | final candidate `meta` | Literal segment texts/timing (only when `save_intermediate: true`) |
| `two_pass_adapt_stats` | final candidate `meta` | `{total, polished, reverted, unchanged}` |
| `two_pass_qc_warning` | candidate or segment `meta` | Drift revert or collapse warning message |
| `literal_text` | segment `meta` | Original literal text for successfully adapted segments |

---

## API

```python
from mt import run_two_pass_translation
from config import Config

config = Config()
# ja_candidate: SubtitleCandidate with Japanese source segments
final_candidate = run_two_pass_translation(ja_candidate, config)

# The literal pass ID is always in meta:
literal_id = final_candidate.meta["literal_pass_candidate_id"]

# Per-segment QC warnings:
for seg in final_candidate.segments:
    if "two_pass_qc_warning" in seg.meta:
        print(f"QC warning at {seg.start:.2f}s: {seg.meta['two_pass_qc_warning']}")
```

To use Pass 2 independently:

```python
from llm_polish import adapt_candidate_from_literal

# literal_candidate is the output of Pass 1 (or any MT candidate)
natural_candidate = adapt_candidate_from_literal(
    literal_candidate, config, ja_candidate=ja_candidate
)
```
