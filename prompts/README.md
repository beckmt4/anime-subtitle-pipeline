# prompts/

Reusable AI prompts used in this repo's development and subtitle pipeline.

Two distinct categories live here:

## 1. Development prompts

Prompts used to generate or significantly shape code, specs, tests, or documentation during development.

Add a development prompt here when:
- It produced a significant chunk of code or a module scaffold
- It is repeatable (you would use the same prompt again for a similar task)
- It reflects a pattern other contributors should follow

**File naming:** `dev-<short-slug>.md`

Example: `dev-module-spec-template.md`, `dev-test-generation-asr.md`

**Minimum content:**

```markdown
# <Prompt title>

**Purpose:** What this prompt is for.
**Used in:** Issue #N / PR #N / <module name>
**Tool:** Claude Code / ChatGPT / etc.

---

<prompt text>

---

**Notes:** What worked, what did not, recommended follow-up prompts.
```

## 2. Pipeline prompts

Prompts used by the subtitle pipeline itself at runtime (LLM polish system prompts, style guides, etc.).

These currently live in `config.yaml` under `llm.prompts`. As the platform grows and domain packs are introduced, pack-specific prompt templates will move here.

**File naming:** `pipeline-<domain>-<style>.md`

Example: `pipeline-anime-natural.md`, `pipeline-jav-literal.md`

## What does NOT go here

- Throwaway interactive prompts used once with no reuse value
- Prompts that contain private or sensitive context
