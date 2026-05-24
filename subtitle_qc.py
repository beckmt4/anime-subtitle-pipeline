"""Subtitle quality-control (QC) validator for SRT artifacts.

Validates generated ``.srt`` files deterministically without requiring any
ML models or external services.  All checks are performed locally using a
built-in pure-Python SRT parser.

Checks
------
1. **parseability** – File is readable UTF-8 and contains at least
   ``min_cues`` cues (default: 1).
2. **out-of-order cues** – Each cue's start time ≥ the previous cue's
   start time.  Out-of-order cues indicate an ASR/MT timing bug.
3. **overlapping cues** – No cue's end time exceeds the following cue's
   start time.  Overlaps cause visual artefacts on most players.
4. **duration violations** – Every cue duration is within
   [``min_duration``, ``max_duration``].
5. **high reading speed** – Characters-per-second (after stripping inline
   formatting) ≤ ``max_cps``.  Cues above this threshold are too fast to
   read comfortably.
6. **formatting artefacts** – Flags ASS/SSA override tags, literal ASS
   inline-newline escapes (``\\N``, ``\\n``, ``\\h``), and HTML tags that
   should not appear in clean SRT output.
7. **line-length violations** – No individual display line exceeds
   ``max_line_chars`` characters.
8. **line-count violations** – No cue contains more than ``max_lines``
   display lines.
9. **translation judge heuristics** – When candidate metadata is supplied,
   flags likely untranslated output, omissions, added meaning, softened
   explicit dialogue, low-confidence markers, and high-risk safety-review
   indicators under the live-action/adult profile.

Default thresholds
------------------
============== ======= =====================================================
Threshold       Value   Rationale
============== ======= =====================================================
min_duration    0.5 s  Below this the cue is too brief to read
max_duration    7.0 s  Above this the viewer has scrolled past the scene
max_cps          20    Industry-standard comfortable reading speed for anime
max_line_chars   42    Two-column broadcast / streaming standard
max_lines         2    Standard two-line subtitle limit
min_cues          1    A valid subtitle file has at least one cue
============== ======= =====================================================

QC summary schema
-----------------
The returned dict is JSON-serialisable::

    {
        "parsed_ok": bool,
        "cue_count": int,
        "violations": [
            {
                "type": str,      # identifier, e.g. "overlap"
                "severity": str,  # "error" | "warning"
                "cue_index": int, # 1-based SRT sequence number; -1 = file-level
                "detail": str,    # human-readable description
            },
            ...
        ],
        "error_count": int,
        "warning_count": int,
        "pass_qc": bool,          # True when error_count == 0
    }

``pass_qc`` is ``False`` whenever *any* error-severity violation is present.
Warnings do not affect ``pass_qc``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.subtitles import SubtitleCandidate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal regex patterns
# ---------------------------------------------------------------------------

# SRT timestamp line: 00:00:01,000 --> 00:00:03,500
# Allows comma or period as the millisecond separator (both are found in the wild).
_TIMESTAMP_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})"
)

# ASS/SSA override blocks: {\an8}, {\pos(100,200)}, etc.
_ASS_OVERRIDE_RE = re.compile(r"\{[^}]*\}")

# Literal ASS inline newlines that should have been converted to real newlines.
_ASS_NEWLINE_RE = re.compile(r"\\[nNh]")

# HTML elements (including self-closing).
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")

_ADULT_JA_MARKERS = (
    "セックス",
    "チン",
    "まんこ",
    "乳首",
    "フェラ",
    "中出し",
    "挿入",
    "勃起",
    "射精",
    "オナニー",
    "エロ",
    "犯す",
    "やる",
)
_ADULT_EN_MARKERS = (
    "fuck",
    "fucking",
    "sex",
    "cock",
    "dick",
    "pussy",
    "cum",
    "blowjob",
    "masturbat",
    "penis",
    "vagina",
    "horny",
    "nipple",
)
_LOW_CONFIDENCE_MARKERS = (
    "[low_confidence]",
    "[uncertain]",
    "[inaudible]",
    "not sure",
    "unclear",
    "can't hear",
    "couldn't hear",
    "???",
)
_HIGH_RISK_MARKERS = (
    "未成年",
    "児童",
    "子供",
    "少女",
    "少年",
    "同意なし",
    "無理やり",
    "強姦",
    "レイプ",
    "minor",
    "underage",
    "child",
    "without consent",
    "non-consensual",
    "coerc",
    "forced",
    "rape",
)

# ---------------------------------------------------------------------------
# Severity constants
# ---------------------------------------------------------------------------

_SEVERITY_ERROR = "error"
_SEVERITY_WARNING = "warning"

# ---------------------------------------------------------------------------
# Pure-Python SRT parser
# ---------------------------------------------------------------------------


def _parse_srt_content(
    content: str,
) -> Tuple[bool, List[Tuple[int, float, float, str]]]:
    """Parse raw SRT text; return *(parsed_ok, cues)*.

    Each cue is a tuple ``(sequence_number, start_s, end_s, text)``.
    Returns ``(False, [])`` when no parseable cue blocks are found.
    """
    # Normalise line endings
    content = content.replace("\r\n", "\n").replace("\r", "\n").strip()

    cues: List[Tuple[int, float, float, str]] = []
    for block in re.split(r"\n\s*\n", content):
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue

        # Line 0: sequence number
        try:
            seq = int(lines[0].strip())
        except ValueError:
            continue

        # Line 1: timestamps
        ts_match = _TIMESTAMP_RE.match(lines[1].strip())
        if ts_match is None:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, ts_match.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0

        # Lines 2+: cue text (may span multiple lines)
        text = "\n".join(lines[2:])
        cues.append((seq, start, end, text))

    return (len(cues) > 0, cues)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_formatting(text: str) -> str:
    """Return plain text after removing ASS overrides, inline newlines, and HTML tags."""
    text = _ASS_OVERRIDE_RE.sub("", text)
    text = _ASS_NEWLINE_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub("", text)
    return text.strip()


def _make_violation(
    type_: str,
    severity: str,
    cue_index: int,
    detail: str,
) -> Dict[str, Any]:
    return {
        "type": type_,
        "severity": severity,
        "cue_index": cue_index,
        "detail": detail,
    }


def _contains_any_marker(text: str, markers: Tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _build_summary(
    parsed_ok: bool,
    cue_count: int,
    violations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    error_count = sum(1 for v in violations if v["severity"] == _SEVERITY_ERROR)
    warning_count = sum(1 for v in violations if v["severity"] == _SEVERITY_WARNING)
    return {
        "parsed_ok": parsed_ok,
        "cue_count": cue_count,
        "violations": violations,
        "error_count": error_count,
        "warning_count": warning_count,
        "pass_qc": parsed_ok and error_count == 0,
    }


def _add_translation_judge_warnings(
    candidate: SubtitleCandidate,
    cue_count: int,
    violations: List[Dict[str, Any]],
) -> None:
    dialogue_profile = str(candidate.meta.get("translation_dialogue_profile", "default"))
    flag_low_confidence = bool(
        candidate.meta.get(
            "translation_flag_low_confidence",
            dialogue_profile == "live_action_adult",
        )
    )
    flag_high_risk_content = bool(
        candidate.meta.get(
            "translation_flag_high_risk_content",
            dialogue_profile == "live_action_adult",
        )
    )
    for idx, seg in enumerate(candidate.segments[:cue_count], start=1):
        source_text = ""
        if isinstance(seg.meta, dict):
            source_text = str(
                seg.meta.get("source_text_ja")
                or seg.meta.get("source_text")
                or ""
            )
        source_text = source_text.strip()
        translated_text = seg.text.strip()

        if translated_text and _CJK_RE.search(translated_text):
            violations.append(
                _make_violation(
                    "translation_possible_untranslated",
                    _SEVERITY_WARNING,
                    idx,
                    "Output still contains CJK characters; translation may have failed",
                )
            )

        if not source_text or not translated_text:
            continue

        source_len = len(source_text)
        translated_len = len(translated_text)
        length_ratio = translated_len / max(source_len, 1)
        if source_len >= 10 and length_ratio < 0.30:
            violations.append(
                _make_violation(
                    "translation_possible_omission",
                    _SEVERITY_WARNING,
                    idx,
                    (
                        f"Translated cue is much shorter than source "
                        f"(ratio={length_ratio:.2f}); possible omission"
                    ),
                )
            )
        if source_len <= 8 and translated_len >= 40 and length_ratio > 3.5:
            violations.append(
                _make_violation(
                    "translation_possible_added_meaning",
                    _SEVERITY_WARNING,
                    idx,
                    (
                        f"Translated cue is much longer than source "
                        f"(ratio={length_ratio:.2f}); possible added meaning"
                    ),
                )
            )

        if dialogue_profile == "live_action_adult":
            if any(token in source_text for token in _ADULT_JA_MARKERS):
                lowered = translated_text.lower()
                if not any(token in lowered for token in _ADULT_EN_MARKERS):
                    violations.append(
                        _make_violation(
                            "translation_possible_softened_adult_dialogue",
                            _SEVERITY_WARNING,
                            idx,
                            (
                                "Live-action/adult profile source appears explicit, "
                                "but translation may be softened or euphemized"
                            ),
                        )
                    )

        if flag_low_confidence and _contains_any_marker(
            translated_text, _LOW_CONFIDENCE_MARKERS
        ):
            violations.append(
                _make_violation(
                    "translation_low_confidence_flagged",
                    _SEVERITY_WARNING,
                    idx,
                    "Translation line is flagged as uncertain and should be reviewed",
                )
            )

        if flag_high_risk_content and _contains_any_marker(
            f"{source_text}\n{translated_text}", _HIGH_RISK_MARKERS
        ):
            violations.append(
                _make_violation(
                    "translation_high_risk_content_review",
                    _SEVERITY_WARNING,
                    idx,
                    (
                        "Potential minor/coercion/illegal-content indicator detected; "
                        "manual safety review required"
                    ),
                )
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_qc(
    srt_path: str | Path,
    *,
    candidate: SubtitleCandidate | None = None,
    min_duration: float = 0.5,
    max_duration: float = 7.0,
    max_cps: float = 20.0,
    max_line_chars: int = 42,
    max_lines: int = 2,
    min_cues: int = 1,
    ocr_confidence_warn_below: float = 0.70,
) -> Dict[str, Any]:
    """Run all subtitle QC checks and return a machine-readable summary dict.

    Args:
        srt_path: Path to the SRT file to validate.
        candidate: Optional candidate that produced the SRT. When supplied,
            ASR-origin warning metadata on each segment is copied into QC
            findings so translated lines can be traced back to weak ASR input.
        min_duration: Minimum allowed cue duration in seconds (default 0.5).
        max_duration: Maximum allowed cue duration in seconds (default 7.0).
        max_cps: Maximum reading speed in characters per second (default 20).
        max_line_chars: Maximum characters per display line (default 42).
        max_lines: Maximum number of display lines per cue (default 2).
        min_cues: Minimum required number of cues (default 1).
        ocr_confidence_warn_below: OCR confidence threshold below which cues
            are flagged as warning-level low-confidence OCR output.

    Returns:
        A JSON-serialisable QC summary dict.  See module docstring for the
        full schema.  ``pass_qc`` is ``True`` when no error-severity
        violations are found.
    """
    path = Path(srt_path)
    violations: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 1. Read & parse
    # ------------------------------------------------------------------
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        violations.append(
            _make_violation(
                "parse_failed", _SEVERITY_ERROR, -1, f"Cannot read file: {exc}"
            )
        )
        return _build_summary(parsed_ok=False, cue_count=0, violations=violations)

    parsed_ok, cues = _parse_srt_content(content)
    if not cues:
        violations.append(
            _make_violation(
                "parse_failed",
                _SEVERITY_ERROR,
                -1,
                "SRT file contains no parseable cue blocks",
            )
        )
        return _build_summary(parsed_ok=False, cue_count=0, violations=violations)

    cue_count = len(cues)

    # ------------------------------------------------------------------
    # 2. Cue count
    # ------------------------------------------------------------------
    if cue_count < min_cues:
        violations.append(
            _make_violation(
                "too_few_cues",
                _SEVERITY_ERROR,
                -1,
                f"Found {cue_count} cue(s); expected at least {min_cues}",
            )
        )

    # ------------------------------------------------------------------
    # 3–8. Per-cue checks
    # ------------------------------------------------------------------
    for i, (seq, start, end, text) in enumerate(cues):
        cue_idx = seq  # use the SRT sequence number for human-readable reference

        # 3. Out-of-order
        if i > 0:
            _prev_seq, prev_start, _prev_end, _prev_text = cues[i - 1]
            if start < prev_start:
                violations.append(
                    _make_violation(
                        "out_of_order",
                        _SEVERITY_ERROR,
                        cue_idx,
                        f"Cue starts at {start:.3f}s, before previous cue start "
                        f"{prev_start:.3f}s",
                    )
                )

        # 4. Overlap with previous cue
        if i > 0:
            _prev_seq2, _prev_start2, prev_end, _prev_text2 = cues[i - 1]
            if prev_end > start:
                violations.append(
                    _make_violation(
                        "overlap",
                        _SEVERITY_ERROR,
                        cue_idx,
                        f"Cue starts at {start:.3f}s but previous cue ends at "
                        f"{prev_end:.3f}s (overlap: {prev_end - start:.3f}s)",
                    )
                )

        # 5. Duration violations
        duration = end - start
        if duration < min_duration:
            violations.append(
                _make_violation(
                    "duration_too_short",
                    _SEVERITY_ERROR,
                    cue_idx,
                    f"Duration {duration:.3f}s < minimum {min_duration}s",
                )
            )
        elif duration > max_duration:
            violations.append(
                _make_violation(
                    "duration_too_long",
                    _SEVERITY_ERROR,
                    cue_idx,
                    f"Duration {duration:.3f}s > maximum {max_duration}s",
                )
            )

        # 6. High CPS
        plain = _strip_formatting(text)
        # Count printable characters excluding real newlines that split display lines
        plain_chars = len(plain.replace("\n", ""))
        if duration > 0 and plain_chars > 0:
            cps = plain_chars / duration
            if cps > max_cps:
                violations.append(
                    _make_violation(
                        "high_cps",
                        _SEVERITY_WARNING,
                        cue_idx,
                        f"Reading speed {cps:.1f} CPS > maximum {max_cps} CPS",
                    )
                )

        # 7. Formatting artifacts
        if _ASS_OVERRIDE_RE.search(text):
            violations.append(
                _make_violation(
                    "formatting_artifact",
                    _SEVERITY_ERROR,
                    cue_idx,
                    "ASS/SSA override tag found in cue text",
                )
            )
        if _ASS_NEWLINE_RE.search(text):
            violations.append(
                _make_violation(
                    "formatting_artifact",
                    _SEVERITY_ERROR,
                    cue_idx,
                    r"Literal ASS inline newline escape (\N, \n, \h) found in cue text",
                )
            )
        if _HTML_TAG_RE.search(text):
            violations.append(
                _make_violation(
                    "formatting_artifact",
                    _SEVERITY_WARNING,
                    cue_idx,
                    "HTML tag found in cue text",
                )
            )

        # 8. Line length and line count
        display_lines = plain.splitlines() if plain else []
        if len(display_lines) > max_lines:
            violations.append(
                _make_violation(
                    "too_many_lines",
                    _SEVERITY_WARNING,
                    cue_idx,
                    f"Cue has {len(display_lines)} display lines (maximum: {max_lines})",
                )
            )
        for line in display_lines:
            if len(line) > max_line_chars:
                preview = line[:30] + ("..." if len(line) > 30 else "")
                violations.append(
                    _make_violation(
                        "line_too_long",
                        _SEVERITY_WARNING,
                        cue_idx,
                        f"Line has {len(line)} characters (maximum: {max_line_chars}): "
                        f"{preview!r}",
                    )
                )

    # 9. ASR-origin warning passthrough
    if candidate is not None:
        _add_translation_judge_warnings(candidate, cue_count, violations)

        for idx, seg in enumerate(candidate.segments[:cue_count], start=1):
            asr_meta = seg.meta.get("asr") if isinstance(seg.meta, dict) else None
            if not asr_meta:
                asr_meta = None
            if asr_meta:
                for warning in asr_meta.get("warnings", []):
                    violations.append(
                        _make_violation(
                            "asr_low_confidence",
                            _SEVERITY_WARNING,
                            idx,
                            (
                                f"ASR warning {warning.get('type', 'unknown')}: "
                                f"{warning.get('detail', 'low confidence source segment')}"
                            ),
                        )
                    )

            if isinstance(seg.meta, dict) and "ocr_confidence" in seg.meta:
                try:
                    conf = float(seg.meta.get("ocr_confidence"))
                except (TypeError, ValueError):
                    conf = 0.0
                if conf < ocr_confidence_warn_below:
                    violations.append(
                        _make_violation(
                            "ocr_low_confidence",
                            _SEVERITY_WARNING,
                            idx,
                            (
                                f"OCR confidence {conf:.2f} is below threshold "
                                f"{ocr_confidence_warn_below:.2f}"
                            ),
                        )
                    )

        for warning in candidate.meta.get("asr_source_warnings", []):
            violations.append(
                _make_violation(
                    "asr_source_warning",
                    _SEVERITY_WARNING,
                    -1,
                    warning.get("detail", "ASR source selection warning"),
                )
            )

    summary = _build_summary(
        parsed_ok=parsed_ok, cue_count=cue_count, violations=violations
    )

    if summary["pass_qc"]:
        logger.info(
            "QC PASS — %d cue(s), %d warning(s): %s",
            cue_count,
            summary["warning_count"],
            path.name,
        )
    else:
        logger.warning(
            "QC FAIL — %d error(s), %d warning(s): %s",
            summary["error_count"],
            summary["warning_count"],
            path.name,
        )

    return summary


__all__ = ["run_qc"]
