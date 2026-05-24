# Issue specs — MVP recovery

These files are GitHub-issue-ready specs written under the original P0/P1 naming
scheme.  All have since been created as GitHub issues under the Epic 01–08
numbering.  See `docs/BACKLOG.md` for the spec-to-issue mapping table.

## Spec files and corresponding GitHub issues

| # | Spec file | GitHub issue |
|---|-----------|--------------|
| 1 | `p0-a1-reopen-roadmap-with-accurate-issue-states.md` | #178 (01-C) |
| 2 | `p0-a2-define-mvp-release-gate-checklist.md` | — (not yet created) |
| 3 | `p0-b1-remove-hardcoded-ja-en-from-core-mt.md` | #179 (02-A) |
| 4 | `p0-b2-remove-text-ja-assumptions-in-core-polish.md` | #204 (07-C) |
| 5 | `p0-b3-generalize-benchmark-language-routing.md` | #78 (02-B) |
| 6 | `p0-c1-ship-reference-default-ocr-backend.md` | #181 (03-A) |
| 7 | `p0-c2-ocr-confidence-routing-review-visibility.md` | #184 (03-D) |
| 8 | `p1-d1-review-state-machine-and-dedupe.md` | #189 (04-E) |
| 9 | `p1-d2-approved-artifact-lifecycle.md` | #187 (04-C) |
| 10 | `p1-e1-processing-queue-and-worker-cli.md` | #191 (05-A) |
| 11 | `p1-e2-recursive-scanner-and-dedupe.md` | #192 (05-B) |
| 12 | `p1-f1-add-explicit-smoke-test-module.md` | #207 (08-A) |
| 13 | `p1-f2-unskip-language-hardcoding-guards.md` | #208 (08-B) |
| 14 | `p1-f3-branch-protection-and-release-baseline.md` | #210 (08-D) |

## Quick create command
```bash
gh issue create --title "<title>" --body-file docs/issues/<file>.md
```

Use labels/milestones at creation time based on your board conventions.
