# acceptance/

Acceptance checklists and criteria definitions for issues and features.

## Purpose

An acceptance document is the written definition of done for a specific issue or feature. It is written before or alongside implementation, not after. It is what the PR checklist points to.

Keeping these as separate files (rather than only in GitHub issues) means:
- They are version-controlled alongside the code
- They can be referenced from multiple PRs
- They survive issue tracker changes or migrations
- AI tools can read them directly during implementation

## File naming

```
acceptance/<issue-number>-<short-slug>.md
```

Examples:
- `acceptance/29-language-pack-interface.md`
- `acceptance/18-artifact-registry.md`
- `acceptance/22-review-workflow.md`

## Minimum content

```markdown
# Acceptance criteria — Issue #N: <title>

**Issue:** #N
**Status:** draft | ready | met

## Criteria

- [ ] <specific, testable criterion>
- [ ] <specific, testable criterion>
- [ ] ...

## Test evidence

<!-- Filled in when the issue is closed. -->
<!-- What was run, what passed, what was observed. -->

## Notes

<!-- Assumptions, deferred items, caveats. -->
```

## How this connects to PRs

The PR template includes an acceptance checklist section. That section should either:
- Reference a file in `acceptance/` (`see acceptance/29-language-pack-interface.md`)
- Or paste the criteria inline if the issue has no separate acceptance doc

Both are valid. The criteria must be visible and checked. They must not be skipped.

## Relationship to specs

- `specs/` = the plan (written before implementation)
- `acceptance/` = the criteria (written before or during implementation, verified on completion)

A spec may include acceptance criteria inline. Once a spec is approved and implementation begins, those criteria can be extracted to `acceptance/` so the PR template can reference them independently.
