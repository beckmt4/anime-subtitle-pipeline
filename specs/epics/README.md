# specs/epics/

Epic-level specifications for work that is planned but not yet implemented.

Each file in this directory describes one epic's remaining tasks, acceptance
criteria, and suggested implementation approach. These are the GitHub issues
waiting to be created (or the detail behind already-open issues).

## Files

| File | Epic | Status |
|------|------|--------|
| `epic-01-product-truth.md` | Docs and roadmap truth (remaining) | Partially done; tasks A–C outstanding |
| `epic-02-translation-quality.md` | Translation quality productization (remaining) | Tasks A–C outstanding |
| `epic-03-ocr-capability.md` | OCR as a real product capability | All tasks outstanding |
| `epic-04-review-workflow.md` | Review workflow beta hardening | All tasks outstanding |
| `epic-05-library-automation.md` | Library-scale automation | All tasks outstanding |
| `epic-06-anime-domain-pack.md` | Anime domain pack maturity v1 | All tasks outstanding |
| `epic-07-multi-language-proof.md` | Multi-language platform proof | All tasks outstanding |
| `epic-08-ci-hardening.md` | CI, test, and release hardening (remaining) | Tasks A–D outstanding |

## How to use these files

1. Pick a task from the appropriate epic file.
2. Create a GitHub issue with the acceptance criteria from the task.
3. Reference the spec file in the issue body.
4. When the issue is complete, create an `acceptance/<issue-number>-<slug>.md`
   with test evidence.
5. Update `docs/BACKLOG.md` to check off the item.
6. Update `acceptance/acceptance-test-index.md` to link the new acceptance file.

## Priority order

Follow the priority order in `docs/BACKLOG.md`:

1. Epic 01 remaining (docs cleanup)
2. Epic 02 remaining (translation quality)
3. Epic 04 (review workflow hardening)
4. Epic 03 (OCR)
5. Epic 06 (anime domain pack)
6. Epic 05 (library automation)
7. Epic 07 (multi-language proof)
8. Epic 08 remaining (CI hardening)
