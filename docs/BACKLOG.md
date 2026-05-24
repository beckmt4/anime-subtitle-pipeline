# Backlog tracker — MVP recovery plan

## Purpose
Track the practical MVP-recovery backlog for delivery by a mostly junior team.

This backlog is source-of-truth for issue creation order and should stay aligned
with `docs/issues/*.md`.

## Current status
- The repository is **advanced alpha**, not MVP-complete.
- Several prior epic issues are closed while substantive gaps remain.
- This backlog re-baselines work into explicit P0/P1 issue specs.

## Priority order

### P0-A — MVP truth reset and release gate recovery
1. **A1** Reopen roadmap with accurate issue states  
   Spec: `docs/issues/p0-a1-reopen-roadmap-with-accurate-issue-states.md`
2. **A2** Define MVP release gate checklist  
   Spec: `docs/issues/p0-a2-define-mvp-release-gate-checklist.md`

### P0-B — Core language-agnostic hardening
3. **B1** Remove hardcoded JA→EN prompt/metadata from `core/mt`  
   Spec: `docs/issues/p0-b1-remove-hardcoded-ja-en-from-core-mt.md`
4. **B2** Remove `text_ja` assumptions in `core/polish`  
   Spec: `docs/issues/p0-b2-remove-text-ja-assumptions-in-core-polish.md`
5. **B3** Generalize benchmark off JP/EN-only assumptions  
   Spec: `docs/issues/p0-b3-generalize-benchmark-language-routing.md`

### P0-C — OCR capability completion for MVP
6. **C1** Ship reference default OCR backend  
   Spec: `docs/issues/p0-c1-ship-reference-default-ocr-backend.md`
7. **C2** OCR confidence + routing + review visibility  
   Spec: `docs/issues/p0-c2-ocr-confidence-routing-review-visibility.md`

### P1-D — Review workflow production hardening
8. **D1** Review state machine + dedupe  
   Spec: `docs/issues/p1-d1-review-state-machine-and-dedupe.md`
9. **D2** Approved artifact lifecycle  
   Spec: `docs/issues/p1-d2-approved-artifact-lifecycle.md`

### P1-E — Library automation and repeatable batch execution
10. **E1** SQLite processing queue and worker CLI mode  
    Spec: `docs/issues/p1-e1-processing-queue-and-worker-cli.md`
11. **E2** Recursive scanner + skip/force/hash dedupe  
    Spec: `docs/issues/p1-e2-recursive-scanner-and-dedupe.md`

### P1-F — CI and operational safety
12. **F1** Add explicit smoke test module for core paths  
    Spec: `docs/issues/p1-f1-add-explicit-smoke-test-module.md`
13. **F2** Unskip architecture guards for language hardcoding  
    Spec: `docs/issues/p1-f2-unskip-language-hardcoding-guards.md`
14. **F3** Branch protection and release baseline  
    Spec: `docs/issues/p1-f3-branch-protection-and-release-baseline.md`

## Definition of done
A backlog item is done only when:
- implementation is merged
- non-integration CI is green
- acceptance criteria in the issue spec are satisfied
- relevant docs are updated
- acceptance evidence is linked in `acceptance/`
