# Backlog tracker — Subtitle Intelligence Platform

## Purpose

Single source-of-truth for active work priority.  
Replaces the former roadmap tracker (#15, now closed).

This file must stay aligned with actual GitHub issue states.  
Last verified: 2026-05-24.

## Current status

- The repository is **advanced alpha** with core generate/benchmark workflows
  functional and language-pack architecture merged.
- Epics 01 (product truth reset) through 08 (CI hardening) define the current
  work breakdown.
- Prior epic tracker #15 is **closed** — this backlog supersedes it.

---

## Active work — ordered by epic

### Epic 01 — Product truth and roadmap reset

| # | Title | State |
|---|-------|-------|
| #176 | 01-A — Fix stale import examples in docs/QUICK_REFERENCE.md | ✅ Closed |
| #177 | 01-B — Fix stale import examples in docs/API_DOCUMENTATION.md | ✅ Closed |
| #178 | 01-C — Verify GitHub issue state matches docs/BACKLOG.md | 🔄 Open |

### Epic 02 — Translation quality hardening

| # | Title | State |
|---|-------|-------|
| #179 | 02-A — Generalize LLMDirectTranslator prompts in core/mt/__init__.py | 🔄 Open |
| #78  | 02-B — Translation benchmark corpus and model comparison reports | 🔄 Open |
| #180 | 02-C — Two-pass production safety validation | 🔄 Open |

Legacy issues (closed, completed in prior phases):
- #74 — Direct context-aware LLM translation engine ✅
- #75 — Translation engine selector and hybrid routing ✅
- #76 — Literal-first and natural-subtitle second-pass workflow ✅
- #77 — Live-action and adult-dialogue translation profile ✅
- #79 — Translation QC judge ✅
- #81 — Local model and hardware evaluation matrix ✅

### Epic 03 — OCR and subtitle source completeness

| # | Title | State |
|---|-------|-------|
| #181 | 03-A — Choose and document a default local OCR backend | 🔄 Open |
| #182 | 03-B — Bitmap subtitle extraction pipeline | 🔄 Open |
| #183 | 03-C — OCR test fixtures | 🔄 Open |
| #184 | 03-D — OCR review routing and UI integration | 🔄 Open |

Parent epic: #21 (open)

### Epic 04 — Review workflow production hardening

| # | Title | State |
|---|-------|-------|
| #185 | 04-A — Review CLI polish | 🔄 Open |
| #186 | 04-B — Review UI improvements | 🔄 Open |
| #187 | 04-C — Approved-output lifecycle | 🔄 Open |
| #188 | 04-D — Translation memory quality gates | 🔄 Open |
| #189 | 04-E — Review task deduplication and state machine | 🔄 Open |
| #190 | 04-F — Review workflow tests | 🔄 Open |

Parent epic: #22 (open)

### Epic 05 — Library automation and batch execution

| # | Title | State |
|---|-------|-------|
| #191 | 05-A — Persistent processing queue (SQLite-backed) | 🔄 Open |
| #192 | 05-B — Recursive library scanner | 🔄 Open |
| #193 | 05-C — Worker mode | 🔄 Open |
| #194 | 05-D — Status / reporting CLI | 🔄 Open |
| #195 | 05-E — Artifact registry integration | 🔄 Open |
| #196 | 05-F — Library automation tests | 🔄 Open |

Parent epic: #25 (open)

### Epic 06 — Anime domain pack

| # | Title | State |
|---|-------|-------|
| #197 | 06-A — Anime glossary and name fixtures | 🔄 Open |
| #198 | 06-B — Honorific policy | 🔄 Open |
| #199 | 06-C — Signs, songs, and OP/ED policy | 🔄 Open |
| #200 | 06-D — Anime benchmark fixtures | 🔄 Open |
| #201 | 06-E — Anime source-selection tuning | 🔄 Open |

Parent epic: #23 (open)

### Epic 07 — Multi-language expansion

| # | Title | State |
|---|-------|-------|
| #202 | 07-A — en_en transcription-only pack | 🔄 Open |
| #203 | 07-B — Add one second real translation pack (ko_en or zh_en) | 🔄 Open |
| #204 | 07-C — Remove hardcoded ja/en assumptions from core modules | 🔄 Open |
| #205 | 07-D — Language-specific quality hooks | 🔄 Open |
| #206 | 07-E — Docs: which packs are real vs. planned | 🔄 Open |

Parent epic: #27 (open)

Legacy issues (closed, completed in prior phases):
- #55 — Refactor Japanese-only generate orchestration into language-pack routing hooks ✅
- #26 — Introduce language-pack architecture for multi-language expansion ✅

### Epic 08 — CI, test, and release hardening

| # | Title | State |
|---|-------|-------|
| #207 | 08-A — Consolidated smoke-test suite | 🔄 Open |
| #208 | 08-B — Architecture guard: no hardcoded ja/en in core/mt | 🔄 Open |
| #209 | 08-C — Acceptance-test index maintenance | 🔄 Open |
| #210 | 08-D — Branch protection and required CI | 🔄 Open |

Parent epic: #106 (open)

---

## Closed epics (completed)

| # | Title |
|---|-------|
| #15 | Backlog tracker — ordered Subtitle Intelligence Platform roadmap |
| #16 | Re-architect anime-subtitle-pipeline into a subtitle intelligence platform |
| #17 | Establish AI-assisted development workflow and repo standards |
| #18 | Add persistent state, artifact registry, and processing ledger |
| #19 | Harden generate mode into a production-grade source selection engine |
| #20 | Harden benchmark mode into a core product capability |
| #24 | Create JAV domain pack v1 with privacy-aware operation |
| #26 | Introduce language-pack architecture for multi-language expansion |

---

## Mapping: old P0/P1 spec files → current issues

The `docs/issues/` directory contains spec files written under the former P0/P1
naming scheme. Below is the mapping to current GitHub issues:

| Spec file | Current issue |
|-----------|---------------|
| `p0-a1-reopen-roadmap-with-accurate-issue-states.md` | #178 (01-C, this work) |
| `p0-a2-define-mvp-release-gate-checklist.md` | No issue created yet |
| `p0-b1-remove-hardcoded-ja-en-from-core-mt.md` | #179 (02-A) |
| `p0-b2-remove-text-ja-assumptions-in-core-polish.md` | #204 (07-C) |
| `p0-b3-generalize-benchmark-language-routing.md` | #78 (02-B) |
| `p0-c1-ship-reference-default-ocr-backend.md` | #181 (03-A) |
| `p0-c2-ocr-confidence-routing-review-visibility.md` | #184 (03-D) |
| `p1-d1-review-state-machine-and-dedupe.md` | #189 (04-E) |
| `p1-d2-approved-artifact-lifecycle.md` | #187 (04-C) |
| `p1-e1-processing-queue-and-worker-cli.md` | #191 (05-A) |
| `p1-e2-recursive-scanner-and-dedupe.md` | #192 (05-B) |
| `p1-f1-add-explicit-smoke-test-module.md` | #207 (08-A) |
| `p1-f2-unskip-language-hardcoding-guards.md` | #208 (08-B) |
| `p1-f3-branch-protection-and-release-baseline.md` | #210 (08-D) |

---

## Definition of done

A backlog item is done only when:
- implementation is merged
- non-integration CI is green
- acceptance criteria in the issue spec are satisfied
- relevant docs are updated
- acceptance evidence is linked in `acceptance/`
