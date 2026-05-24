# Epic 03 — OCR as a real product capability

**Status:** CLI wiring complete (`acceptance/21-bitmap-ocr-cli-wiring.md`).
No default backend exists; bring-your-own only. Bitmap extraction pipeline
and OCR fixtures are missing.

**Parent:** beckmt4/anime-subtitle-pipeline#21

**Backlog reference:** `docs/BACKLOG.md` Phase 4, item 30

---

## Tasks

### Task 03-A — Choose and document a default local OCR backend

**What:** Select one OCR library to serve as the reference backend so that
users can enable OCR without writing their own backend class.

**Candidate options:**
- **PaddleOCR** — supports Japanese + English, line detection built-in
- **Tesseract** — widely available, good English OCR, Japanese quality varies
- **EasyOCR** — good multi-language support, easy Python install
- **Subtitle-specific extraction** — PGS/VobSub image extraction + any of the above

**Decision criteria:**
- Installable via `pip` or documented system package
- License compatible with the project
- Reasonable Japanese OCR quality (for JA bitmap subs)
- Works on CPU without GPU requirement for CI

**Acceptance criteria:**
- [ ] Decision recorded in `docs/architecture/` (update `adr-002-pack-model.md`
      or a new ADR)
- [ ] Backend class implemented in `core/ocr/` or as a reference pack
- [ ] Install instructions added to README or `docs/QUICKSTART.md`
- [ ] Fails clearly when dependencies are missing (informative error, not traceback)

---

### Task 03-B — Bitmap subtitle extraction pipeline

**What:** Extract individual cue images from PGS (`.sup`) or VobSub (`.sub`/`.idx`)
bitmap subtitle tracks, paired with their timestamps, so OCR can process them.

**Acceptance criteria:**
- [ ] Extract bitmap subtitle images with accurate start/end timestamps
- [ ] Run OCR per cue via the configured backend
- [ ] Reconstruct `SubtitleCandidate` with per-segment `meta.ocr_confidence`
- [ ] Store per-segment OCR confidence; low-confidence density propagates to QC
- [ ] Extraction tested without real video (synthetic fixtures or mocked ffmpeg)

---

### Task 03-C — OCR test fixtures

**What:** No synthetic bitmap subtitle fixtures exist. Tests cannot verify the
OCR path end-to-end.

**Acceptance criteria:**
- [ ] At least 3 tiny synthetic bitmap subtitle images:
  - Clear English text
  - Clear Japanese text
  - Low-confidence (blurry or noisy) text
- [ ] Tests cover:
  - OCR disabled → bitmap sources skipped cleanly
  - OCR enabled but backend missing → informative error
  - Valid backend + English bitmap → SRT output
  - Valid backend + Japanese bitmap → OCR → MT → SRT output
  - Low-confidence OCR → QC warning + review routing

---

### Task 03-D — OCR review routing and UI integration

**What:** Low-confidence OCR outputs should be visible in the review UI so
a human can correct garbled bitmap subtitles.

**Acceptance criteria:**
- [ ] OCR confidence visible in QC JSON sidecar
- [ ] Review task created when OCR warning density exceeds threshold
- [ ] OCR confidence shown in the local HTML review UI per segment
- [ ] `policy.routing.ocr_warn_density_review_threshold` is configurable
