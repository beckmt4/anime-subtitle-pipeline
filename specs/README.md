# specs/

Implementation specs and design notes scoped to a specific issue or capability.

## When to write a spec

Write a spec before implementing anything non-trivial. A spec is not a design document for its own sake — it is the written agreement on what you are building and how you will know it is done.

Required for:
- New modules or significant refactors
- Changes that affect more than one module
- Anything that involves a design decision that is not obvious from the code

Not required for:
- Pure bug fixes with a clear root cause
- Documentation-only changes
- Trivial one-file changes

## File naming

```
specs/<issue-number>-<short-slug>.md
```

Examples:
- `specs/29-language-pack-interface.md`
- `specs/18-artifact-registry-schema.md`

## Minimum content

A spec should cover:

1. **Problem** — what gap or capability this addresses
2. **Scope** — what is in and out of scope for this implementation
3. **Design** — the approach, data shapes, interfaces, or module interactions
4. **Acceptance criteria** — what done looks like (may reference `acceptance/`)
5. **Open questions** — anything unresolved before implementation starts

## Relationship to other folders

- `specs/` = the plan before implementation
- `acceptance/` = the criteria used to verify completion
- `prompts/` = the AI prompts used to help generate or refine the spec or implementation
- `fixtures/` = the test data the implementation will be validated against
