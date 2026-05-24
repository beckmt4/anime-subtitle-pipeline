# MVP release gates

Use this checklist as the release go/no-go contract.

## Gate 1 — Core generate reliability
- [ ] Generate reliably produces `.en.srt` for:
  - [ ] embedded EN text subtitle path
  - [ ] EN audio ASR path
  - [ ] JP text subtitle MT path
  - [ ] JP audio ASR→MT path
- Evidence:
  - [ ] Tests
  - [ ] Acceptance doc link
  - [ ] Latest CI run link

## Gate 2 — OCR posture is explicit
- [ ] OCR is either:
  - [ ] productized with a documented default backend, or
  - [ ] explicitly unsupported in MVP docs/CLI with clear behavior
- [ ] OCR enable/skip/failure behavior is user-visible and actionable
- Evidence:
  - [ ] Docs link
  - [ ] Tests/acceptance link

## Gate 3 — SQLite lineage and deterministic state
- [ ] Each run persists deterministic pipeline lineage (media/run/candidate/artifact).
- [ ] Review task state and candidate linkage are queryable.
- Evidence:
  - [ ] Artifact/ledger test link
  - [ ] Sample output link

## Gate 4 — Review stability for weak outputs
- [ ] Review routing is deterministic and policy-driven.
- [ ] Approve/reject (and dedupe/state behavior) are tested.
- Evidence:
  - [ ] Tests/acceptance link

## Gate 5 — CI safety net
- [ ] Non-integration CI is green.
- [ ] Explicit smoke suite exists and runs in CI.
- [ ] Architecture hardening guards are active (not skipped) for language assumptions.
- Evidence:
  - [ ] CI run link
  - [ ] Test file links

## Gate 6 — Automation baseline
- [ ] Basic queue worker supports discover→queued→running→completed/failed/review_required.
- [ ] Worker status/retry/resume controls exist.
- Evidence:
  - [ ] CLI docs link
  - [ ] Queue/worker tests link

## Release decision
- [ ] All six gates pass.
- [ ] Release notes include evidence links for each gate.
