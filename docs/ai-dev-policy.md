# AI-Assisted Development Policy

This document defines how AI tools are used in this repository.

AI tools do a meaningful share of the development work here. That makes this policy load-bearing, not ceremonial. Every contributor — human or AI — is expected to follow it.

Related: [CONTRIBUTING.md](../CONTRIBUTING.md) covers the full contribution workflow.

---

## What AI-assisted development means here

AI tools (Claude Code, ChatGPT, Gemini, Copilot, and equivalents) are used to:
- Generate and refactor code
- Write tests and fixtures
- Draft documentation and specs
- Scaffold new modules
- Perform code review passes
- Generate and iterate on prompts

This is normal and expected. The policy governs how AI outputs enter the repo — not whether AI is used.

---

## Allowed uses

| Use | Notes |
|---|---|
| Code generation | Allowed. Output must be read, validated, and tested before commit. |
| Refactoring | Allowed. Diff must be reviewed line by line before commit. |
| Test generation | Allowed. Tests must actually be run and pass before commit. |
| Documentation | Allowed. Content must be verified for accuracy against the actual code. |
| Spec drafting | Allowed. Specs must be reviewed for scope and correctness before landing in `specs/`. |
| Prompt development | Allowed. Prompts used in development go in `prompts/` for reproducibility. |
| Architecture proposals | Allowed. Must be reviewed against existing architecture decisions in `docs/architecture/`. |
| Code review assistance | Allowed as a supplement. Does not replace human review. |

---

## Prohibited and restricted uses

**Never do these:**

- **Blind copy/paste without reading.** Do not commit AI output you have not personally read.
- **Fabricated test results.** Do not claim tests pass if you have not run them. Do not describe test output you did not see.
- **Fabricated file reviews.** Do not claim a file was inspected if you have not read it.
- **Fabricated benchmark results.** Do not include benchmark numbers in docs or comments unless they came from an actual run. Label clearly if synthetic or estimated.
- **Pretending code was executed when it was not.** If a pipeline step was not tested end-to-end, say so.
- **Unverifiable capability claims.** Do not state that an implementation handles a case unless there is a test or you observed it handling that case.

**Proceed with care:**

- AI-generated security-sensitive code (auth, subprocess calls, path handling) must be reviewed more carefully than general logic.
- AI-generated architecture changes must be checked against `docs/architecture/module-boundaries.md`.
- AI-proposed dependency additions must be justified and checked for license compatibility.

---

## Validation requirements

AI output is not done when the AI says it is done. It is done when:

1. **Code was read.** The diff was reviewed line by line by a human.
2. **Tests were run.** `pytest` was executed and passed. Not just written — run.
3. **Acceptance criteria were checked.** The PR template acceptance checklist is complete.
4. **Architecture fit was confirmed.** The change does not violate the module boundaries defined in `docs/architecture/module-boundaries.md`.
5. **Assumptions were documented.** If the AI made a design assumption that narrows future options, it must be noted in the PR body or a spec.

---

## Documenting AI usage in PRs

The PR template includes an AI usage disclosure section. It must be completed honestly.

Acceptable disclosure examples:
- "Claude Code generated the initial draft of `core/asr/__init__.py`. Reviewed diff, ran `pytest test_asr_candidate.py`. All tests pass."
- "Used Claude to refactor `mt.py` translate loop. Verified batch chunking behavior matches prior output on fixture `fixtures/ja_segments_900.json`."
- "No AI tooling used for this change."

Not acceptable:
- "Claude wrote this." (no validation stated)
- Leaving the section blank when AI was used.

---

## Prompts as repo assets

Prompts used to generate or significantly shape implementation work are first-class repo assets.

If you used a prompt that produced a significant result (a module scaffold, a spec, a test suite), put it in `prompts/` with a short header explaining what it was used for and what it produced.

This is not required for one-off interactive sessions, but is required when the prompt is repeatable or reusable (e.g., the prompt used to generate LLM polish prompts, or the spec-generation prompt for a module).

---

## Specs, fixtures, and acceptance as first-class assets

| Asset type | When required |
|---|---|
| `specs/` entry | Any non-trivial feature or module before implementation begins |
| `fixtures/` entry | Any test that needs stable, repeatable input data |
| `acceptance/` entry | Any issue with defined acceptance criteria (reference or copy) |
| `prompts/` entry | Any reusable or repeatable AI prompt that produced significant output |

AI tools should create these assets alongside code, not after the fact.

---

## Commit and PR discipline

- PRs should be bounded. One concern per PR.
- Do not bundle unrelated changes to make a PR easier to merge.
- AI-generated code must appear in a PR, not pushed directly to main.
- Each commit should represent a coherent, reviewable unit. Squash cleanup commits before opening a PR.

---

## Architecture compliance

Before committing a new module, class, or significant function:

1. Check `docs/architecture/module-boundaries.md` for the target module that owns this capability.
2. Confirm the new code lands in the right place.
3. Confirm it does not embed language-specific or domain-specific logic into `core`.
4. If the architecture doc needs updating, update it in the same PR.

AI tools must be explicitly instructed to check the architecture doc before generating module-level code. Do not assume the AI has read it — tell it to.

---

## What counts as human review

A human review means:
- A person read the diff.
- A person ran the tests (or confirmed they ran in CI).
- A person checked the acceptance criteria.

AI-generated review comments, AI-produced summaries of changes, or AI confirmations that code is correct do not count as human review. They can assist, but the human must make the final judgment call.
