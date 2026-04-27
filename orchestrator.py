"""High-level orchestration for the generation flow.

Provides the primary entry point:
- run_generate(media: MediaInfo, cfg: Config, no_llm: bool = False,
               inspect_only: bool = False) -> dict

Generation strategy decision tree (default priorities):
1. If prefer_subtitles and English text subtitles exist → use embedded EN
2. Else if English audio exists and preferred language is EN → EN audio ASR
3. Else if Japanese subtitles exist → JP subtitles → MT (→ optional LLM)
4. Else if Japanese audio exists → JP audio ASR → MT (→ optional LLM)
5. Else fallback to any available audio (EN or JP) → appropriate path

Language probe (auto mode only):
  When only an EN-tagged audio track is found and prefer_audio_language is
  "auto", a 30-second clip is probed with Whisper's language detector before
  the decision tree runs. If Japanese is detected with ≥ 0.85 confidence, the
  track is treated as Japanese and routed through JA ASR → MT, catching files
  where the container metadata language tag is wrong.

Config overrides (config.yaml generate section):
  generate:
    prefer_subtitles: true
    prefer_audio_language: "auto"  # "en" | "ja" | "auto"
    use_llm_polish: true

Executed metadata includes chosen strategy and output SRT path. Inspect-only
metadata includes chosen strategy, planned output paths, and the same
selection_report without running heavy processing steps.
"""
from __future__ import annotations

import copy
import itertools
import logging
from pathlib import Path
from typing import Dict, Any

from config import Config
from media_inspect import MediaInfo
from subtitle_utils import extract_subtitle_track
from audio_utils import extract_audio_with_ffmpeg
from asr import FasterWhisperASR, build_candidate_from_segments
from mt import translate_candidate_jp_to_en
from llm_polish import polish_candidate_with_llm, enforce_constraints_on_candidate
from srt_writer import write_candidate_srt
from models import SubtitleCandidate
from subtitle_qc import run_qc
from tracing import start_span
import uuid
from typing import Optional

from core.artifacts import (
    ArtifactRegistry,
    ArtifactRecord,
    ARTIFACT_TYPE_SRT,
    ARTIFACT_TYPE_QC_JSON,
    CANDIDATE_STATUS_ACCEPTED,
    PIPELINE_STATUS_COMPLETED,
    PIPELINE_STATUS_FAILED,
    PipelineRunRecord,
    SubtitleCandidateRecord,
)
from core.artifacts.pipeline_wiring import open_registry, compute_media_hash  # noqa: F401  (re-exported)
from core.policy import PolicyEngine


logger = logging.getLogger(__name__)


# Audio language probe settings (used when metadata tag is absent or suspect).
_PROBE_DURATION_SEC = 30       # seconds of audio to sample
_PROBE_JA_THRESHOLD = 0.85    # minimum Whisper confidence to reroute
# Sentinel returned by _probe_audio_language when an exception prevents the probe
# from running at all.  Distinct from None (inconclusive / low confidence) so
# callers can log a specific warning and downgrade candidate confidence.
_PROBE_FAILED: str = "probe_failed"

# Confidence tiers describe how much processing uncertainty the selected path
# introduces.  Higher-tier sources require less lossy transformation and are
# expected to be more accurate out of the box.
_STRATEGY_CONFIDENCE_TIER: Dict[str, str] = {
    "embedded_en": "high",
    "en_audio_asr": "medium",
    "embedded_jp_mt": "low",
    "ja_audio_asr_mt": "low",
    "untagged_audio_asr_mt": "very_low",
}

# Base quality scores (0–70) per strategy.  Each step in the processing chain
# (ASR, MT) introduces potential accuracy loss, so strategies that apply more
# transformations receive lower base scores.
#
#   embedded_en         — direct English subtitles; no lossy steps               → 70
#   en_audio_asr        — English audio → ASR (one lossy step)                   → 55
#   embedded_jp_mt      — Japanese subs → MT (one lossy step)                    → 40
#   ja_audio_asr_mt     — Japanese audio → ASR → MT (two lossy steps)            → 30
#   untagged_audio_asr_mt — unknown audio → ASR → MT + source uncertainty        → 15
_STRATEGY_BASE_SCORE: Dict[str, int] = {
    "embedded_en": 70,
    "en_audio_asr": 55,
    "embedded_jp_mt": 40,
    "ja_audio_asr_mt": 30,
    "untagged_audio_asr_mt": 15,
}

# Grade thresholds for the 0–100 total score.
_SCORE_GRADE_THRESHOLDS = [
    (80, "A"),
    (60, "B"),
    (40, "C"),
    (20, "D"),
]

# Strategies that involve machine translation or an untagged fallback should
# be flagged for human review because accuracy cannot be guaranteed.
_REVIEW_RECOMMENDED_STRATEGIES = {"embedded_jp_mt", "ja_audio_asr_mt", "untagged_audio_asr_mt"}


# ISO-639-1 → common ISO-639-2 / localized variants that should all be treated
# as the same language for source-selection purposes. Keep this map small; it
# only needs to cover the languages the pipeline actually branches on.
_LANG_ALIASES = {
    "ja": {"ja", "jpn", "jp", "ja-jp"},
    "en": {"en", "eng", "en-us", "en-gb"},
}


def _lang_matches(stream_lang: str | None, target: str) -> bool:
    """True if stream_lang (raw from container) belongs to target's alias set.

    Handles:
    - Exact codes and known aliases (e.g. 'eng', 'jpn')
    - BCP-47 regional subtags (e.g. 'en-AU', 'en-CA', 'en-US' all match 'en')
    """
    if not stream_lang:
        return False
    code = stream_lang.strip().lower()
    aliases = _LANG_ALIASES.get(target, {target})
    if code in aliases:
        return True
    # BCP-47 prefix: 'en-AU' → prefix 'en', check if prefix is a known alias.
    prefix = code.split("-", 1)[0]
    return prefix in aliases


def _first_text_sub(media: MediaInfo, lang: str) -> int | None:
    for s in media.subtitle_streams:
        if s.is_bitmap:
            logger.debug(
                "  subtitle stream %d (codec=%s lang=%s): skipped — bitmap/image-based track",
                s.index, s.codec, s.language or s.raw_language or "?",
            )
            continue
        raw = s.language or s.raw_language
        if _lang_matches(raw, lang):
            logger.info(
                "  subtitle stream %d (codec=%s lang=%s): ACCEPTED as %s text subtitle",
                s.index, s.codec, raw or "?", lang,
            )
            return s.index
        logger.debug(
            "  subtitle stream %d (codec=%s lang=%s): rejected — does not match target '%s'",
            s.index, s.codec, raw or "?", lang,
        )
    return None


def _first_audio_order(media: MediaInfo, lang: str) -> int | None:
    for order, stream in enumerate(media.audio_streams):
        raw = stream.language or stream.raw_language
        if _lang_matches(raw, lang):
            logger.debug(
                "  audio stream order=%d idx=%d (codec=%s lang=%s): ACCEPTED as %s audio",
                order, stream.index, stream.codec, raw or "?", lang,
            )
            return order
        logger.debug(
            "  audio stream order=%d idx=%d (codec=%s lang=%s): rejected — does not match target '%s'",
            order, stream.index, stream.codec, raw or "?", lang,
        )
    return None


# Title-tag keywords that suggest a track contains Japanese audio.  Matched
# case-insensitively against the track's "title" metadata tag.
_JA_TITLE_KEYWORDS: frozenset[str] = frozenset({
    "japanese", "japan", "jpn", "ja", "日本語",
})


def _select_untagged_audio_fallback(media: MediaInfo) -> tuple[int, str]:
    """Pick the most likely primary audio track when no ja/en language tags exist.

    Applies heuristics in priority order:
    1. A track whose ``title`` metadata tag contains a Japanese language keyword
       (e.g. "Japanese Audio", "JPN", "日本語").
    2. The first stereo (2-channel) track — the primary audio in anime releases
       is almost always stereo, while commentary or secondary tracks are often
       mono or 5.1.
    3. Track 0 as the final catch-all (preserves previous default behaviour).

    Args:
        media: Inspected media information.  ``media.audio_streams`` must not
            be empty.

    Returns:
        A ``(audio_order, reason)`` tuple where *audio_order* is the 0-based
        index into ``media.audio_streams`` and *reason* is a short human-
        readable explanation of the heuristic that was applied.
    """
    # --- Heuristic 1: title tag keyword match ---
    for order, stream in enumerate(media.audio_streams):
        title = (stream.tags.get("title", "")).strip().lower()
        if any(kw in title for kw in _JA_TITLE_KEYWORDS):
            return order, (
                f"title tag contains Japanese keyword "
                f"({stream.tags.get('title')!r})"
            )

    # --- Heuristic 2: first stereo (2-channel) track ---
    for order, stream in enumerate(media.audio_streams):
        if stream.channels == 2:
            return order, (
                f"first stereo (2-channel) track at audio order {order}"
            )

    # --- Heuristic 3: default to track 0 ---
    return 0, "no heuristic match; defaulting to first audio track"


def _log_polish_stats(stats: Dict[str, Any]) -> None:
    """Emit log messages summarising the outcome of a single LLM polish run."""
    status = stats["polish_status"]
    changed = stats["segments_changed"]
    unchanged = stats["segments_unchanged"]
    if status == "fallback":
        logger.info(
            "LLM polish: fallback (LLM unreachable/disabled) — "
            f"{unchanged} segment(s) passed through unchanged"
        )
    elif status == "no_change":
        logger.warning(
            "LLM polish produced no change — all %d segment(s) identical to raw MT",
            unchanged,
        )
    else:
        logger.info(
            "LLM polish: %d segment(s) changed, %d segment(s) unchanged",
            changed,
            unchanged,
        )


def _compare_candidates(raw: SubtitleCandidate, polished: SubtitleCandidate) -> Dict[str, Any]:
    """Compare raw MT and polished candidates segment by segment.

    Returns a dict with keys:
      - polish_status: "changed" | "no_change" | "fallback"
      - segments_changed: number of segments where polished text differs from raw
      - segments_unchanged: number of segments where text is identical

    A "fallback" status means the LLM was unreachable or disabled and the
    polished candidate is a pass-through copy of the raw input.
    """
    if polished.meta.get("fallback"):
        return {
            "polish_status": "fallback",
            "segments_changed": 0,
            "segments_unchanged": len(raw.segments),
        }

    changed = 0
    unchanged = 0
    sentinel = object()
    for raw_seg, pol_seg in itertools.zip_longest(raw.segments, polished.segments, fillvalue=sentinel):
        if raw_seg is sentinel or pol_seg is sentinel:
            # One side has extra segments — that is always a change.
            changed += 1
        elif raw_seg.text.strip() != pol_seg.text.strip():
            changed += 1
        else:
            unchanged += 1

    polish_status = "no_change" if changed == 0 else "changed"
    return {
        "polish_status": polish_status,
        "segments_changed": changed,
        "segments_unchanged": unchanged,
    }


def score_candidate(
    strategy: str,
    candidate: SubtitleCandidate,
    qc_summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Score a subtitle candidate and expose the contributing factors.

    The score is a 0–100 float composed of three additive factors:

    1. **strategy_base** (max 70): Reflects source-type quality.  Direct
       English sources score highest; each additional lossy processing step
       (ASR, MT) reduces the base score.  See ``_STRATEGY_BASE_SCORE`` for the
       per-strategy values.

    2. **qc_pass_rate** (max 20): Fraction of cues that pass QC error checks,
       multiplied by 20.  A perfect QC run yields the full 20 points; each
       error-level violation proportionally reduces this contribution.  When no
       QC summary is available the factor contributes 10 points (neutral).

    3. **segment_yield** (max 10): Rewards a viable segment count.  Full 10
       points are awarded when the candidate contains ≥ 5 segments; fewer
       segments scale linearly down to 0.

    Grade thresholds (based on total_score):
      - A: ≥ 80
      - B: ≥ 60
      - C: ≥ 40
      - D: ≥ 20
      - F: < 20

    Args:
        strategy: The selected generation strategy name
            (e.g. ``"embedded_en"``, ``"ja_audio_asr_mt"``).
        candidate: The ``SubtitleCandidate`` produced by the pipeline.
        qc_summary: Optional QC summary dict returned by ``run_qc``.  When
            provided the ``qc_pass_rate`` factor uses it; otherwise a neutral
            half-score is applied.

    Returns:
        A JSON-serialisable dict with keys:
          - ``total_score``: float in [0, 100]
          - ``grade``: letter grade ("A" | "B" | "C" | "D" | "F")
          - ``factors``: list of factor dicts, each containing:
            - ``name``: factor identifier
            - ``description``: human-readable explanation
            - ``raw_value``: the measured input value
            - ``max_contribution``: maximum points the factor can contribute
            - ``contribution``: actual points added to the total
    """
    factors = []

    # --- Factor 1: strategy_base ---
    base_score = _STRATEGY_BASE_SCORE.get(strategy, 0)
    max_base = max(_STRATEGY_BASE_SCORE.values()) if _STRATEGY_BASE_SCORE else 70
    factors.append({
        "name": "strategy_base",
        "description": (
            "Source type quality — direct English sources score highest; "
            "each additional lossy processing step (ASR, MT) reduces the base score"
        ),
        "raw_value": strategy,
        "max_contribution": max_base,
        "contribution": base_score,
    })

    # --- Factor 2: qc_pass_rate ---
    _MAX_QC = 20
    if qc_summary is not None:
        cue_count = qc_summary.get("cue_count", 0)
        error_count = qc_summary.get("error_count", 0)
        if cue_count > 0:
            pass_rate = 1.0 - min(error_count / cue_count, 1.0)
        else:
            pass_rate = 0.0
        qc_contribution = round(pass_rate * _MAX_QC, 2)
        qc_raw = round(pass_rate, 4)
    else:
        # No QC data; award neutral half-score.
        pass_rate = 0.5
        qc_contribution = round(pass_rate * _MAX_QC, 2)
        qc_raw = None
    factors.append({
        "name": "qc_pass_rate",
        "description": (
            "Fraction of cues free of QC errors "
            "(error violations proportionally reduce this factor)"
        ),
        "raw_value": qc_raw,
        "max_contribution": _MAX_QC,
        "contribution": qc_contribution,
    })

    # --- Factor 3: segment_yield ---
    _MAX_YIELD = 10
    _MIN_VIABLE_SEGMENTS = 5
    seg_count = candidate.segment_count
    yield_ratio = min(seg_count / _MIN_VIABLE_SEGMENTS, 1.0)
    yield_contribution = round(yield_ratio * _MAX_YIELD, 2)
    factors.append({
        "name": "segment_yield",
        "description": (
            f"Candidate has a viable segment count "
            f"(full score at ≥ {_MIN_VIABLE_SEGMENTS} segments)"
        ),
        "raw_value": seg_count,
        "max_contribution": _MAX_YIELD,
        "contribution": yield_contribution,
    })

    # --- Factor 4: ASR warning density penalty ---
    _MAX_ASR_PENALTY = 25
    _FULL_ASR_PENALTY_DENSITY = 0.25
    asr_warning_count = 0
    asr_warning_density = 0.0
    if qc_summary is not None:
        cue_count = qc_summary.get("cue_count", 0)
        violations = qc_summary.get("violations", [])
        asr_warning_count = sum(
            1 for v in violations
            if v.get("type") in {"asr_low_confidence", "asr_source_warning"}
        )
        if cue_count > 0:
            asr_warning_density = asr_warning_count / cue_count
    if asr_warning_count:
        penalty_ratio = min(asr_warning_density / _FULL_ASR_PENALTY_DENSITY, 1.0)
        asr_penalty = round(-penalty_ratio * _MAX_ASR_PENALTY, 2)
        factors.append({
            "name": "asr_warning_density",
            "description": (
                "Penalty for ASR-origin warning density; high density means "
                "translation quality may be limited by weak transcription"
            ),
            "raw_value": round(asr_warning_density, 4),
            "max_contribution": 0,
            "contribution": asr_penalty,
        })

    total = round(sum(f["contribution"] for f in factors), 2)
    total = min(max(total, 0.0), 100.0)

    grade = "F"
    for threshold, letter in _SCORE_GRADE_THRESHOLDS:
        if total >= threshold:
            grade = letter
            break

    return {
        "total_score": total,
        "grade": grade,
        "factors": factors,
        "asr_warning_count": asr_warning_count,
        "asr_warning_density": round(asr_warning_density, 4),
    }


def _log_candidate_score(score: Dict[str, Any]) -> None:
    """Emit a concise candidate score summary to the logger."""
    logger.info(
        "Candidate score: %.1f / 100  (grade %s)",
        score["total_score"],
        score["grade"],
    )
    for f in score["factors"]:
        logger.info(
            "  %-20s  %5.1f / %d  — %s",
            f["name"],
            f["contribution"],
            f["max_contribution"],
            f["description"],
        )


def _build_selection_report(
    strategy: str,
    orig_en_sub_idx: int | None,
    orig_ja_sub_idx: int | None,
    orig_en_audio_order: int | None,
    orig_ja_audio_order: int | None,
    prefer_subtitles: bool,
    prefer_audio_language: str,
    skip_embedded_en: bool,
    audio_track_override: int | None,
    probed_lang: str | None,
    untagged_audio_order: int | None = None,
    source_language: str = "auto",
    source_language_rerouted_order: int | None = None,
) -> Dict[str, Any]:
    """Build a structured explanation of why *strategy* was selected.

    Returns a dict with:
      - selected_source: chosen strategy name
      - confidence_tier: "high" | "medium" | "low" | "very_low"
      - rationale: human-readable explanation of the winning choice
      - sources_evaluated: ordered list of all candidate sources, each with
        their detection status, stream reference, and reason for selection or
        rejection.  Possible status values: "selected", "skipped",
        "not_available".
      - overrides_active: list of override flag names that affected the
        decision (e.g. ["skip_embedded_en", "audio_track_override=2",
        "source_language=ja"])
      - review_recommended: True when the strategy involves a lossy processing
        step (MT / untagged-audio fallback) and human review is advisable
      - review_reason: human-readable justification (None when not recommended)
    """
    overrides_active = []
    sources_evaluated = []

    if source_language != "auto":
        overrides_active.append(f"source_language={source_language}")

    if audio_track_override is not None:
        overrides_active.append(f"audio_track_override={audio_track_override}")
        for src in ("embedded_en", "en_audio_asr", "embedded_jp_mt"):
            sources_evaluated.append({
                "source": src,
                "stream": None,
                "detected": False,
                "status": "skipped",
                "reason": (
                    f"CLI --audio-track {audio_track_override} override active; "
                    "all other sources bypassed"
                ),
            })
        sources_evaluated.append({
            "source": "ja_audio_asr_mt",
            "stream": f"audio:{audio_track_override}",
            "detected": True,
            "status": "selected",
            "reason": (
                f"Forced via --audio-track {audio_track_override}; "
                "specified track treated as Japanese and routed through ASR → MT"
            ),
        })
        rationale = (
            f"CLI --audio-track {audio_track_override} override active. "
            "Specified track forced through Japanese ASR → MT pipeline."
        )
    else:
        if skip_embedded_en:
            overrides_active.append("skip_embedded_en")

        # --- embedded_en ---
        en_sub_detected = orig_en_sub_idx is not None
        if not en_sub_detected:
            en_sub_status = "not_available"
            en_sub_reason = "No English text subtitle stream detected in container"
        elif skip_embedded_en:
            en_sub_status = "skipped"
            en_sub_reason = (
                "skip_embedded_en override active (--extract-en-subs); "
                "bypassed so generation pipeline produces an independent SRT"
            )
        elif not prefer_subtitles:
            en_sub_status = "skipped"
            en_sub_reason = "prefer_subtitles=False in config"
        elif strategy == "embedded_en":
            en_sub_status = "selected"
            en_sub_reason = (
                f"Highest-priority source (stream sub:{orig_en_sub_idx}); "
                "direct English subtitles require no processing"
            )
        else:
            en_sub_status = "skipped"
            en_sub_reason = f"Lower priority than selected source ({strategy})"
        sources_evaluated.append({
            "source": "embedded_en",
            "stream": f"sub:{orig_en_sub_idx}" if en_sub_detected else None,
            "detected": en_sub_detected,
            "status": en_sub_status,
            "reason": en_sub_reason,
        })

        # --- en_audio_asr ---
        # An untagged track promoted to English by the language probe is treated
        # as an effective EN audio source even though orig_en_audio_order is None.
        _untagged_probed_as_en = (
            probed_lang == "en"
            and orig_en_audio_order is None
            and untagged_audio_order is not None
        )
        _effective_en_audio = (
            source_language_rerouted_order
            if source_language == "en" and source_language_rerouted_order is not None
            else (
                orig_en_audio_order
                if orig_en_audio_order is not None
                else (untagged_audio_order if _untagged_probed_as_en else None)
            )
        )
        en_audio_detected = _effective_en_audio is not None
        # Compute probe_rerouted once — reused for both the en_audio and ja_audio entries.
        probe_rerouted = probed_lang == "ja" and orig_ja_audio_order is None
        if not en_audio_detected:
            en_audio_status = "not_available"
            en_audio_reason = "No English audio stream detected in container"
        elif probe_rerouted:
            en_audio_status = "skipped"
            en_audio_reason = (
                f"Language probe detected Japanese content in EN-tagged track "
                f"{orig_en_audio_order} (confidence ≥ {_PROBE_JA_THRESHOLD:.0%}); "
                "rerouted to ja_audio_asr_mt path"
            )
        elif strategy == "en_audio_asr" and source_language == "en":
            en_audio_status = "selected"
            en_audio_reason = (
                f"CLI --source-language=en override active; audio track "
                f"{_effective_en_audio} treated as English and routed through EN ASR"
            )
        elif strategy == "en_audio_asr" and _untagged_probed_as_en:
            en_audio_status = "selected"
            en_audio_reason = (
                f"Untagged audio track {_effective_en_audio} confirmed English by "
                f"language probe (confidence ≥ {_PROBE_JA_THRESHOLD:.0%}); "
                "routed through EN ASR path"
            )
        elif strategy == "en_audio_asr" and prefer_audio_language == "en":
            en_audio_status = "selected"
            en_audio_reason = (
                f"English audio track {_effective_en_audio} selected; "
                "prefer_audio_language=en in config"
            )
        elif strategy == "en_audio_asr":
            en_audio_status = "selected"
            en_audio_reason = (
                f"Fallback: English audio track {_effective_en_audio} selected "
                "(no Japanese sources available)"
            )
        elif prefer_audio_language == "en":
            en_audio_status = "skipped"
            en_audio_reason = f"Lower priority than selected source ({strategy})"
        else:
            en_audio_status = "skipped"
            en_audio_reason = f"Lower priority than selected source ({strategy})"
        sources_evaluated.append({
            "source": "en_audio_asr",
            "stream": f"audio:{_effective_en_audio}" if en_audio_detected else None,
            "detected": en_audio_detected,
            "status": en_audio_status,
            "reason": en_audio_reason,
        })

        # --- embedded_jp_mt ---
        ja_sub_detected = orig_ja_sub_idx is not None
        if not ja_sub_detected:
            ja_sub_status = "not_available"
            ja_sub_reason = "No Japanese text subtitle stream detected in container"
        elif strategy == "embedded_jp_mt":
            ja_sub_status = "selected"
            ja_sub_reason = (
                f"Japanese subtitle stream (sub:{orig_ja_sub_idx}) selected; "
                "fed through MT pipeline → English"
            )
        else:
            ja_sub_status = "skipped"
            ja_sub_reason = f"Lower priority than selected source ({strategy})"
        sources_evaluated.append({
            "source": "embedded_jp_mt",
            "stream": f"sub:{orig_ja_sub_idx}" if ja_sub_detected else None,
            "detected": ja_sub_detected,
            "status": ja_sub_status,
            "reason": ja_sub_reason,
        })

        # --- ja_audio_asr_mt ---
        # The effective JA audio order may have been promoted from:
        #   (a) an EN-tagged track where the probe detected Japanese, or
        #   (b) an untagged track where the probe detected Japanese.
        probe_rerouted_from_en = (
            probed_lang == "ja"
            and orig_ja_audio_order is None
            and orig_en_audio_order is not None
        )
        probe_rerouted_from_untagged = (
            probed_lang == "ja"
            and orig_ja_audio_order is None
            and orig_en_audio_order is None
            and untagged_audio_order is not None
        )
        if source_language == "ja" and source_language_rerouted_order is not None:
            effective_ja_audio = source_language_rerouted_order
        elif probe_rerouted_from_en:
            effective_ja_audio = orig_en_audio_order
        elif probe_rerouted_from_untagged:
            effective_ja_audio = untagged_audio_order
        else:
            effective_ja_audio = orig_ja_audio_order
        # Backward-compat alias: probe_rerouted tracks the EN-mislabeled case only.
        probe_rerouted = probe_rerouted_from_en
        ja_audio_detected = effective_ja_audio is not None
        if not ja_audio_detected:
            ja_audio_status = "not_available"
            ja_audio_reason = "No Japanese audio stream detected in container"
        elif strategy == "ja_audio_asr_mt":
            ja_audio_status = "selected"
            if source_language == "ja" and source_language_rerouted_order is not None:
                ja_audio_reason = (
                    f"CLI --source-language=ja override active; audio track "
                    f"{effective_ja_audio} treated as Japanese and routed through ASR → MT"
                )
            elif probe_rerouted_from_en:
                ja_audio_reason = (
                    f"EN-tagged audio track {effective_ja_audio} rerouted by "
                    f"language probe (detected Japanese, confidence ≥ "
                    f"{_PROBE_JA_THRESHOLD:.0%}); processed via ASR → MT → English"
                )
            elif probe_rerouted_from_untagged:
                ja_audio_reason = (
                    f"Untagged audio track {effective_ja_audio} confirmed Japanese by "
                    f"language probe (confidence ≥ {_PROBE_JA_THRESHOLD:.0%}); "
                    "processed via ASR → MT → English"
                )
            else:
                ja_audio_reason = (
                    f"Japanese audio track {effective_ja_audio} selected; "
                    "fed through ASR → MT pipeline → English"
                )
        elif prefer_audio_language == "en":
            ja_audio_status = "skipped"
            ja_audio_reason = (
                "prefer_audio_language='en' in config; "
                "Japanese audio path not preferred"
            )
        else:
            ja_audio_status = "skipped"
            ja_audio_reason = f"Lower priority than selected source ({strategy})"
        sources_evaluated.append({
            "source": "ja_audio_asr_mt",
            "stream": f"audio:{effective_ja_audio}" if ja_audio_detected else None,
            "detected": ja_audio_detected,
            "status": ja_audio_status,
            "reason": ja_audio_reason,
        })

        # --- untagged_audio_asr_mt (only shown when it was selected) ---
        if strategy == "untagged_audio_asr_mt":
            _untagged_order_val = untagged_audio_order if untagged_audio_order is not None else 0
            sources_evaluated.append({
                "source": "untagged_audio_asr_mt",
                "stream": f"audio:{_untagged_order_val}",
                "detected": True,
                "status": "selected",
                "reason": (
                    "Last-resort fallback: no language-tagged streams found; "
                    f"track {_untagged_order_val} "
                    "treated as Japanese and routed via ASR → MT"
                ),
            })

        # Derive rationale from the winning entry
        selected_entry = next(
            (s for s in sources_evaluated if s["status"] == "selected"), None
        )
        if selected_entry is None:
            # This should never happen if the decision tree and sources list are in
            # sync; raise here so any future logic errors surface immediately.
            raise AssertionError(
                f"_build_selection_report: no source marked 'selected' "
                f"for strategy '{strategy}'"
            )
        rationale = selected_entry["reason"]

        # Prepend a probe context note when the probe drove the decision
        if probe_rerouted_from_untagged:
            rationale = (
                f"Language probe confirmed Japanese in untagged audio:{untagged_audio_order}: "
                + rationale
            )
        elif probe_rerouted:
            rationale = (
                f"Language probe overrode container tag on audio:{orig_en_audio_order}: "
                + rationale
            )

    confidence_tier = _STRATEGY_CONFIDENCE_TIER.get(strategy)
    if confidence_tier is None:
        logger.warning(
            "_build_selection_report: strategy '%s' is not in _STRATEGY_CONFIDENCE_TIER; "
            "confidence tier will be reported as 'unknown'",
            strategy,
        )
        confidence_tier = "unknown"
    review_recommended = strategy in _REVIEW_RECOMMENDED_STRATEGIES
    review_reason = (
        "MT pipeline output (machine translation); manual review recommended for accuracy"
        if review_recommended
        else None
    )

    return {
        "selected_source": strategy,
        "confidence_tier": confidence_tier,
        "rationale": rationale,
        "sources_evaluated": sources_evaluated,
        "overrides_active": overrides_active,
        "review_recommended": review_recommended,
        "review_reason": review_reason,
    }


def _log_selection_report(report: Dict[str, Any]) -> None:
    """Emit a human-readable source-selection report to the logger."""
    logger.info("-" * 50)
    logger.info("SOURCE SELECTION REPORT")
    logger.info(
        "  Selected : %s  (confidence: %s)",
        report["selected_source"],
        report["confidence_tier"],
    )
    logger.info("  Rationale: %s", report["rationale"])
    if report["overrides_active"]:
        logger.info("  Overrides: %s", ", ".join(report["overrides_active"]))
    logger.info("  Candidates evaluated:")
    for src in report["sources_evaluated"]:
        if src["status"] == "selected":
            marker = "✓"
        elif src["status"] == "not_available":
            marker = "✗"
        else:
            marker = "⊘"
        stream_info = f" [{src['stream']}]" if src.get("stream") else ""
        logger.info(
            "    %s %-25s%s — %s",
            marker,
            src["source"],
            stream_info,
            src["reason"],
        )
    if report["review_recommended"]:
        logger.warning("  ⚠ Review recommended: %s", report["review_reason"])
    logger.info("-" * 50)


def _add_asr_source_warning(
    candidate: SubtitleCandidate,
    *,
    type_: str,
    detail: str,
) -> None:
    """Attach a file/track-level ASR source warning to a candidate."""
    warning = {"type": type_, "severity": "warning", "detail": detail}
    candidate.meta.setdefault("asr_source_warnings", []).append(warning)
    quality = candidate.meta.setdefault("asr_quality", {})
    source_warnings = quality.setdefault("source_warnings", [])
    source_warnings.append(warning)
    quality["warning_count"] = quality.get("warning_count", 0) + 1
    if quality.get("status") == "clean":
        quality["status"] = "warn"
    if candidate.meta.get("asr_quality_status") == "clean":
        candidate.meta["asr_quality_status"] = "warn"


_PROPAGATED_ASR_META_KEYS = (
    "asr_quality",
    "asr_quality_status",
    "asr_low_confidence_segment_count",
    "asr_source_warnings",
)


def _propagate_asr_meta(parent: SubtitleCandidate, child: SubtitleCandidate) -> None:
    """Preserve ASR source metadata across MT/polish stages."""
    for key in _PROPAGATED_ASR_META_KEYS:
        if key in parent.meta and key not in child.meta:
            child.meta[key] = copy.deepcopy(parent.meta[key])


def _asr_quality_summary(candidate: SubtitleCandidate) -> Dict[str, Any]:
    """Return the ASR quality summary from a candidate, or a clean default."""
    quality = candidate.meta.get("asr_quality")
    if isinstance(quality, dict):
        return dict(quality)
    return {
        "status": "not_applicable",
        "segment_count": candidate.segment_count,
        "low_confidence_segment_count": 0,
        "low_confidence_ratio": 0.0,
        "warning_count": 0,
        "summary_warnings": [],
    }


def _translation_model_version(candidate: SubtitleCandidate, cfg: Config) -> str:
    return (
        candidate.meta.get("translation_model")
        or candidate.meta.get("model")
        or cfg.mt_model_name
    )


def _probe_audio_language(
    video_path: Path,
    audio_order: int,
    cfg: Config,
) -> str | None:
    """Extract a short clip and probe its language with Whisper.

    Used when the container's language tag may be wrong (e.g., Japanese audio
    labelled 'en'). Extracts the first _PROBE_DURATION_SEC seconds, runs
    Whisper's language detector, and returns the detected language code if
    confidence exceeds _PROBE_JA_THRESHOLD, otherwise None.
    """
    probe_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_probe_a{audio_order}.wav"
    try:
        extract_audio_with_ffmpeg(
            str(video_path), str(probe_path), audio_order,
            duration_sec=_PROBE_DURATION_SEC,
        )
        asr = FasterWhisperASR(cfg)
        lang, prob = asr.detect_language(str(probe_path))
        asr.unload_model()
        logger.info(
            "Language probe (track %d, first %ds): detected '%s' (confidence=%.2f)",
            audio_order, _PROBE_DURATION_SEC, lang, prob,
        )
        if prob >= _PROBE_JA_THRESHOLD:
            return lang
        logger.info(
            "Language probe inconclusive (confidence %.2f < threshold %.2f)",
            prob, _PROBE_JA_THRESHOLD,
        )
        return None
    except Exception as exc:
        logger.warning(
            "Language probe failed: %s — stream metadata tag will be used; "
            "candidate confidence will be downgraded",
            exc,
        )
        return _PROBE_FAILED
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except PermissionError:
            logger.debug("Could not delete temp file %s (PermissionError)", probe_path)


# ---------------------------------------------------------------------------
# Registry helpers — all calls are wrapped in try/except.  A registry failure
# must never crash the pipeline; at worst we log a warning and return None.
# ---------------------------------------------------------------------------

def _reg_start_run(
    registry: Optional[ArtifactRegistry],
    media_hash: Optional[str],
    cfg,
    run_id: str,
) -> Optional[int]:
    """Create a PipelineRunRecord and return its DB id, or None on failure."""
    if registry is None or not media_hash:
        return None
    try:
        import json as _json
        config_snapshot: dict = {}
        try:
            config_snapshot = {
                "profile": cfg.profile,
                "asr_model": cfg.asr_model_name,
                "mt_model": cfg.mt_model_name,
                "llm_model": cfg.llm_model_name,
                "llm_enabled": cfg.llm_enabled,
            }
        except Exception:
            pass
        rec = PipelineRunRecord(
            run_id=run_id,
            media_hash=media_hash,
            config=config_snapshot,
        )
        stored = registry.create_pipeline_run(rec)
        return stored.id
    except Exception as exc:
        logger.warning("ArtifactRegistry: failed to start run — %s", exc)
        return None


def _reg_finish_run(
    registry: Optional[ArtifactRegistry],
    run_id_str: Optional[str],
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """Mark a pipeline run as completed or failed.

    Args:
        run_id_str: The UUID string run_id assigned at run start (not the
                    integer DB primary key). Matches finish_pipeline_run's
                    contract in ArtifactRegistry.
    """
    if registry is None or not run_id_str:
        return
    try:
        registry.finish_pipeline_run(run_id_str, status=status, error_message=error_message)
    except Exception as exc:
        logger.warning("ArtifactRegistry: failed to finish run %s — %s", run_id_str, exc)


def _reg_store_candidate(
    registry: Optional[ArtifactRegistry],
    media_hash: Optional[str],
    candidate,  # models.SubtitleCandidate
    source: str,
    model_version: str = "",
    parent_id: Optional[int] = None,
) -> Optional[int]:
    """Persist a SubtitleCandidate and return its DB id, or None on failure.

    Args:
        registry:      Open ArtifactRegistry, or None (no-op).
        media_hash:    SHA-256 hex digest of the source media file.
        candidate:     models.SubtitleCandidate produced by the pipeline.
        source:        One of 'asr', 'embedded', 'mt', 'mt_llm'.
        model_version: Model identifier string (e.g. Whisper model name).
        parent_id:     DB id of the candidate this was derived from, if any.

    Returns:
        Integer DB id of the stored record, or None if the registry is
        unavailable or an error occurred.
    """
    if registry is None or not media_hash:
        return None
    try:
        segments = [
            {"start": s.start, "end": s.end, "text": s.text, "meta": dict(s.meta)}
            for s in candidate.segments
        ]
        rec = SubtitleCandidateRecord(
            media_hash=media_hash,
            source_id=candidate.id,
            language=candidate.language,
            source=source,
            origin_stream=candidate.origin_stream,
            model_version=model_version,
            segments=segments,
            meta=dict(candidate.meta),
            status=CANDIDATE_STATUS_ACCEPTED,
            parent_candidate_id=parent_id,
        )
        stored = registry.store_candidate(rec)
        logger.debug(
            "ArtifactRegistry: stored candidate %s (db_id=%s, parent=%s)",
            candidate.id, stored.id, parent_id,
        )
        return stored.id
    except Exception as exc:
        logger.warning(
            "ArtifactRegistry: failed to store candidate %s — %s",
            candidate.id, exc,
        )
        return None


def _reg_store_artifact(
    registry: Optional[ArtifactRegistry],
    media_hash: Optional[str],
    artifact_type: str,
    file_path,  # Path or str
    candidate_db_id: Optional[int] = None,
    run_db_id: Optional[int] = None,
) -> Optional[int]:
    """Persist an output file record and return its DB id, or None on failure."""
    if registry is None or not media_hash:
        return None
    try:
        import hashlib as _hashlib
        from pathlib import Path as _Path
        p = _Path(file_path)
        file_hash: Optional[str] = None
        if p.exists():
            h = _hashlib.sha256()
            with open(p, "rb") as fh:
                while chunk := fh.read(1 << 20):
                    h.update(chunk)
            file_hash = h.hexdigest()
        rec = ArtifactRecord(
            media_hash=media_hash,
            artifact_type=artifact_type,
            file_path=str(file_path),
            candidate_id=candidate_db_id,
            pipeline_run_id=run_db_id,
            file_hash=file_hash,
        )
        stored = registry.store_artifact(rec)
        logger.debug(
            "ArtifactRegistry: stored artifact %s -> %s (db_id=%s)",
            artifact_type, p.name, stored.id,
        )
        return stored.id
    except Exception as exc:
        logger.warning(
            "ArtifactRegistry: failed to store artifact %s — %s",
            artifact_type, exc,
        )
        return None


def run_generate(
    media: MediaInfo,
    cfg: Config,
    no_llm: bool = False,
    audio_track_override: int | None = None,
    skip_embedded_en: bool = False,
    registry: Optional[ArtifactRegistry] = None,
    media_hash: Optional[str] = None,
    inspect_only: bool = False,
    source_language: str = "auto",
) -> Dict[str, Any]:
    """Production generation flow selecting best available source for EN subtitles.

    Args:
        media: Inspected media info for the input video.
        cfg: Loaded Config.
        no_llm: When True, force-skip LLM polish regardless of config. This mirrors
            the CLI --no-llm flag so generate-mode honors it (previously the flag
            was silently ignored in this path).
        audio_track_override: When not None, bypass the language-based decision tree
            entirely and treat the specified audio track index as Japanese audio
            (ja_audio_asr_mt path). Mirrors the CLI --audio-track flag, which was
            previously only honored by the legacy subtitle mode.
        source_language: When not 'auto', treat the audio source as this language
            regardless of container metadata.  This overrides the language probe and
            re-routes audio to the appropriate ASR path (e.g. 'ja' → ja_audio_asr_mt,
            'en' → en_audio_asr).  Mirrors the CLI --source-language flag.
        skip_embedded_en: When True, ignore any embedded English subtitle tracks and
            force the pipeline through ASR → MT (→ LLM). Used with --extract-en-subs
            so the extracted embedded subs and the freshly generated subs can be
            compared or used for training.
        inspect_only: When True, perform source discovery and strategy planning
            only. No ASR, MT, LLM, subtitle extraction, QC, artifact registry,
            or output-file writes are executed.
        registry: Optional open ArtifactRegistry.  When provided, every
            SubtitleCandidate, PipelineRun, and output ArtifactRecord is
            persisted with full lineage (ASR → MT → LLM parent_candidate_id
            chain).  Pass None (the default) to run without persistence —
            the pipeline behaviour is identical either way.
        media_hash: SHA-256 hex digest of the input video file, used as the
            natural key in the registry.  Required when registry is not None;
            ignored otherwise.  Compute with
            ``core.artifacts.pipeline_wiring.compute_media_hash(path)``.

    Returns a metadata dict containing strategy, candidate info, and output paths.
    """
    video_path = media.path
    prefer_subtitles = cfg.get("generate", "prefer_subtitles", default=True)
    prefer_audio_language = cfg.get("generate", "prefer_audio_language", default="auto")
    use_llm_polish = (
        cfg.get("generate", "use_llm_polish", default=True)
        and cfg.llm_enabled
        and not no_llm
    )
    if no_llm:
        logger.info("LLM polish disabled via --no-llm (CLI override)")
    if inspect_only:
        logger.info("Inspect-only mode enabled: planning generate flow without execution")

    logger.info("=" * 70)
    logger.info(f"GENERATE MODE: {video_path.name}")
    logger.info("=" * 70)

    # Detect available sources
    en_sub_idx = _first_text_sub(media, "en")
    ja_sub_idx = _first_text_sub(media, "ja")
    en_audio_order = _first_audio_order(media, "en")
    ja_audio_order = _first_audio_order(media, "ja")

    # Capture original detection results before any overrides or probe mutations
    # so the selection report can explain what was originally seen in the container.
    orig_en_sub_idx = en_sub_idx
    orig_ja_sub_idx = ja_sub_idx
    orig_en_audio_order = en_audio_order
    orig_ja_audio_order = ja_audio_order
    probed_lang: str | None = None
    source_language_rerouted_order: int | None = None
    # Set to True when the probe was attempted on an EN-tagged track but crashed
    # (as opposed to simply returning a low-confidence / inconclusive result).
    # Used to attach a language_probe_failed source warning to the EN ASR candidate
    # so its confidence is downgraded rather than silently trusting metadata.
    _probe_of_en_track_failed: bool = False
    # Audio order of the track chosen as the untagged fallback candidate; set
    # whenever the untagged branch is entered (including via probe).
    selected_untagged_audio_order: int | None = None

    logger.info(
        f"Sources detected: en_sub={en_sub_idx} ja_sub={ja_sub_idx} en_audio={en_audio_order} ja_audio={ja_audio_order}"
    )

    # --- CLI --source-language override ---
    # When the user provides an explicit source language, skip the probe entirely
    # and re-route audio to the appropriate language path.  Container metadata is
    # treated as a hint only; the user's choice takes precedence.
    if source_language != "auto" and audio_track_override is None:
        _all_audio_orders = list(range(len(media.audio_streams)))
        if _all_audio_orders:
            # Prefer a track already tagged with the target language; fall back to
            # the first available track if none match.
            _preferred_order = next(
                (
                    o for o in _all_audio_orders
                    if _lang_matches(
                        media.audio_streams[o].language or media.audio_streams[o].raw_language,
                        source_language,
                    )
                ),
                _all_audio_orders[0],
            )
            _container_tag = (
                media.audio_streams[_preferred_order].language
                or media.audio_streams[_preferred_order].raw_language
                or "none"
            )
            logger.info(
                "CLI --source-language=%s: treating audio track %d as %s "
                "(container language tag: %r); skipping language probe.",
                source_language, _preferred_order, source_language, _container_tag,
            )
            source_language_rerouted_order = _preferred_order
            if source_language == "en":
                en_audio_order = _preferred_order
                ja_audio_order = None
            else:
                ja_audio_order = _preferred_order
                en_audio_order = None

    # When auto-routing and the only audio found is EN-tagged (no JA track),
    # probe the actual audio content so mislabeled Japanese files are routed
    # through the JA ASR → MT path instead of being silently transcribed as
    # English gibberish.
    if (
        not inspect_only
        and source_language == "auto"
        and
        audio_track_override is None
        and prefer_audio_language == "auto"
        and ja_audio_order is None
        and en_audio_order is not None
    ):
        probed_lang = _probe_audio_language(video_path, en_audio_order, cfg)
        if probed_lang == _PROBE_FAILED:
            logger.warning(
                "Language probe failed for EN-tagged track %d — "
                "stream metadata will be trusted without verification; "
                "candidate confidence will be downgraded.",
                en_audio_order,
            )
            _probe_of_en_track_failed = True
            # Normalize to None so that the routing conditions below
            # (probed_lang == "ja" / "en") and _build_selection_report behave
            # identically to the inconclusive-probe case.  The failure is
            # surfaced through the _probe_of_en_track_failed flag instead,
            # which adds a language_probe_failed warning to the candidate.
            probed_lang = None
        elif probed_lang == "ja":
            logger.warning(
                "Language probe detected Japanese in EN-tagged audio track %d — "
                "rerouting through JA ASR → MT path (container tag is likely wrong).",
                en_audio_order,
            )
            ja_audio_order = en_audio_order
            en_audio_order = None
        elif probed_lang == "en":
            logger.info(
                "Language probe confirmed English in track %d — keeping EN ASR path.",
                en_audio_order,
            )

    elif (
        not inspect_only
        and source_language == "auto"
        and
        audio_track_override is None
        and prefer_audio_language == "auto"
        and ja_audio_order is None
        and en_audio_order is None
        and media.audio_streams
    ):
        # No language-tagged audio found at all.  Select the best untagged
        # candidate using heuristics, then probe its language so the pipeline
        # can take the appropriate named path (ja_audio_asr_mt or en_audio_asr)
        # rather than the low-confidence untagged_audio_asr_mt fallback.
        _fallback_order, _fallback_reason = _select_untagged_audio_fallback(media)
        selected_untagged_audio_order = _fallback_order
        _track_count = len(media.audio_streams)
        if _track_count > 1:
            logger.warning(
                "Tagging ambiguous: %d audio tracks found with no recognized "
                "language tag. Selected track %d for language probe (%s). "
                "Use --audio-track N to override.",
                _track_count, _fallback_order, _fallback_reason,
            )
        else:
            logger.info(
                "No language-tagged audio found; probing track %d (%s) to "
                "determine language.",
                _fallback_order, _fallback_reason,
            )
        _probed_untagged_lang = _probe_audio_language(video_path, _fallback_order, cfg)
        if _probed_untagged_lang == "ja":
            logger.warning(
                "Language probe confirmed Japanese in untagged audio track %d "
                "(container tag: %r) — upgrading to ja_audio_asr_mt path.",
                _fallback_order,
                (media.audio_streams[_fallback_order].raw_language or "none"),
            )
            ja_audio_order = _fallback_order
            probed_lang = "ja"
        elif _probed_untagged_lang == "en":
            logger.info(
                "Language probe detected English in untagged audio track %d "
                "(container tag: %r) — routing through en_audio_asr path.",
                _fallback_order,
                (media.audio_streams[_fallback_order].raw_language or "none"),
            )
            en_audio_order = _fallback_order
            probed_lang = "en"
        else:
            if _probed_untagged_lang == _PROBE_FAILED:
                logger.warning(
                    "Language probe failed for untagged audio track %d — "
                    "will fall back to untagged_audio_asr_mt (treating as Japanese).",
                    _fallback_order,
                )
            else:
                logger.warning(
                    "Language probe inconclusive for untagged audio track %d — "
                    "will fall back to untagged_audio_asr_mt (treating as Japanese).",
                    _fallback_order,
                )

    # --extract-en-subs: embedded EN subs were already written to outbox by the
    # caller; skip them here so the pipeline runs ASR → MT (→ LLM) and produces
    # an independently generated SRT for comparison / training use.
    if skip_embedded_en and en_sub_idx is not None:
        logger.info(
            "skip_embedded_en=True: bypassing embedded EN subtitles, "
            "forcing generation pipeline for comparison output."
        )
        en_sub_idx = None

    # CLI --audio-track override: if set, short-circuit the decision tree and
    # force the chosen track through the ja_audio_asr → MT (→ LLM) path. This
    # is what the user already asked for; don't second-guess with language tags.
    if audio_track_override is not None:
        if audio_track_override < 0 or audio_track_override >= len(media.audio_streams):
            raise RuntimeError(
                f"--audio-track {audio_track_override} out of range "
                f"(file has {len(media.audio_streams)} audio stream(s))"
            )
        logger.info(
            f"CLI --audio-track override: forcing track {audio_track_override} "
            f"through Japanese ASR → MT path"
        )
        ja_audio_order = audio_track_override
        # Zero out the upstream branches so the decision tree can't pick them.
        en_sub_idx = None
        ja_sub_idx = None
        en_audio_order = None

    if inspect_only:
        if prefer_subtitles and en_sub_idx is not None:
            strategy = "embedded_en"
        elif prefer_audio_language == "en" and en_audio_order is not None:
            strategy = "en_audio_asr"
        elif ja_sub_idx is not None:
            strategy = "embedded_jp_mt"
        elif prefer_audio_language in ["ja", "auto"] and ja_audio_order is not None:
            strategy = "ja_audio_asr_mt"
        elif en_audio_order is not None:
            strategy = "en_audio_asr"
        elif media.audio_streams:
            strategy = "untagged_audio_asr_mt"
            if selected_untagged_audio_order is None:
                selected_untagged_audio_order, _ = _select_untagged_audio_fallback(media)
        else:
            raise RuntimeError(
                "No usable source found for English subtitle generation "
                "(file has no audio or subtitle streams)"
            )

        selection_report = _build_selection_report(
            strategy=strategy,
            orig_en_sub_idx=orig_en_sub_idx,
            orig_ja_sub_idx=orig_ja_sub_idx,
            orig_en_audio_order=orig_en_audio_order,
            orig_ja_audio_order=orig_ja_audio_order,
            prefer_subtitles=prefer_subtitles,
            prefer_audio_language=prefer_audio_language,
            skip_embedded_en=skip_embedded_en,
            audio_track_override=audio_track_override,
            probed_lang=probed_lang,
            untagged_audio_order=selected_untagged_audio_order,
            source_language=source_language,
            source_language_rerouted_order=source_language_rerouted_order,
        )
        _log_selection_report(selection_report)

        out_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.en.srt"
        qc_path = Path(cfg.get_path("outbox")) / f"{video_path.stem}.en.qc.json"
        return {
            "video": str(video_path.name),
            "strategy": strategy,
            "inspect_only": True,
            "executed": False,
            "planned_output_srt": str(out_srt),
            "planned_qc_json": str(qc_path),
            "selection_report": selection_report,
            "registry_run_id": None,
        }

    # --- Registry: start pipeline run record ---
    _run_id = uuid.uuid4().hex
    _run_db_id = _reg_start_run(registry, media_hash, cfg, run_id=_run_id)

    try:
        strategy = None
        candidate: SubtitleCandidate | None = None
        _final_db_id: Optional[int] = None
        polish_stats: Dict[str, Any] | None = None

        # Decision tree
        if prefer_subtitles and en_sub_idx is not None:
            strategy = "embedded_en"
            logger.info("Strategy: Use embedded English subtitles")
            with start_span("extract_embedded_en"):
                candidate = extract_subtitle_track(video_path, en_sub_idx, language="en",
                                                   output_dir=Path(cfg.get_path("temp")))
            _final_db_id = _reg_store_candidate(
                registry, media_hash, candidate, source="embedded",
            )
        elif prefer_audio_language == "en" and en_audio_order is not None:
            strategy = "en_audio_asr"
            logger.info("Strategy: English audio ASR")
            with start_span("extract_en_audio"):
                audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_en_a{en_audio_order}.wav"
                extract_audio_with_ffmpeg(str(video_path), str(audio_path), en_audio_order)
            with start_span("asr_en_audio"):
                asr = FasterWhisperASR(cfg)
                _asr_lang = source_language if source_language != "auto" else "en"
                segments, _ = asr.transcribe_audio_to_segments(str(audio_path), language=_asr_lang)
                candidate = build_candidate_from_segments(
                    segments,
                    cfg,
                    candidate_id=f"en_audio_asr_a{en_audio_order}",
                    language="en",
                    origin_stream=f"audio:{en_audio_order}",
                )
            try:
                audio_path.unlink(missing_ok=True)
            except PermissionError:
                logger.debug("Could not delete temp file %s (PermissionError)", audio_path)
            _final_db_id = _reg_store_candidate(
                registry, media_hash, candidate, source="asr",
                model_version=cfg.asr_model_name,
            )
        elif ja_sub_idx is not None:
            strategy = "embedded_jp_mt"
            logger.info("Strategy: Japanese subtitles → MT → EN")
            with start_span("extract_embedded_jp"):
                ja_candidate = extract_subtitle_track(video_path, ja_sub_idx, language="ja",
                                                      output_dir=Path(cfg.get_path("temp")))
            _ja_db_id = _reg_store_candidate(
                registry, media_hash, ja_candidate, source="embedded",
            )
            with start_span("mt_embedded_jp"):
                mt_candidate = translate_candidate_jp_to_en(ja_candidate, cfg)
            _mt_db_id = _reg_store_candidate(
                registry, media_hash, mt_candidate, source="mt",
                model_version=_translation_model_version(mt_candidate, cfg), parent_id=_ja_db_id,
            )
            # Always write raw MT output regardless of whether LLM polish runs.
            raw_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.raw.en.srt"
            write_candidate_srt(mt_candidate, str(raw_srt), cfg)
            logger.info(f"Saved pre-polish translation output: {raw_srt.name}")
            if use_llm_polish:
                with start_span("llm_polish_embedded_jp"):
                    polished = polish_candidate_with_llm(mt_candidate, cfg, ja_candidate=ja_candidate)
                    # polish_candidate_with_llm already appends "_llm"; do not re-tag here.
                    candidate = enforce_constraints_on_candidate(polished, cfg)
                polish_stats = _compare_candidates(mt_candidate, candidate)
                _log_polish_stats(polish_stats)
                _final_db_id = _reg_store_candidate(
                    registry, media_hash, candidate, source="mt_llm",
                    model_version=cfg.llm_model_name, parent_id=_mt_db_id,
                )
            else:
                candidate = mt_candidate
                _final_db_id = _mt_db_id
        elif (prefer_audio_language in ["ja", "auto"] and ja_audio_order is not None):
            strategy = "ja_audio_asr_mt"
            logger.info("Strategy: Japanese audio → ASR → MT → EN")
            with start_span("extract_ja_audio"):
                audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_ja_a{ja_audio_order}.wav"
                extract_audio_with_ffmpeg(str(video_path), str(audio_path), ja_audio_order)
            with start_span("asr_ja_audio"):
                asr = FasterWhisperASR(cfg)
                _asr_lang = source_language if source_language != "auto" else "ja"
                segments, _ = asr.transcribe_audio_to_segments(str(audio_path), language=_asr_lang)
                ja_asr_candidate = build_candidate_from_segments(
                    segments,
                    cfg,
                    candidate_id=f"ja_audio_asr_a{ja_audio_order}",
                    language=_asr_lang,
                    origin_stream=f"audio:{ja_audio_order}",
                )
                if audio_track_override is not None:
                    _add_asr_source_warning(
                        ja_asr_candidate,
                        type_="audio_track_override",
                        detail=(
                            f"ASR used CLI-forced audio track {audio_track_override}; "
                            "container language metadata was bypassed"
                        ),
                    )
                elif source_language != "auto":
                    _add_asr_source_warning(
                        ja_asr_candidate,
                        type_="source_language_override",
                        detail=(
                            f"ASR used CLI-forced source language '{source_language}'; "
                            "container language metadata was bypassed"
                        ),
                    )
                elif probed_lang == "ja" and orig_ja_audio_order is None:
                    _add_asr_source_warning(
                        ja_asr_candidate,
                        type_="language_probe_reroute",
                        detail=(
                            f"ASR used audio track {ja_audio_order} after language probe "
                            "overrode missing or conflicting container metadata"
                        ),
                    )
            try:
                audio_path.unlink(missing_ok=True)
            except PermissionError:
                logger.debug("Could not delete temp file %s (PermissionError)", audio_path)
            _asr_db_id = _reg_store_candidate(
                registry, media_hash, ja_asr_candidate, source="asr",
                model_version=cfg.asr_model_name,
            )
            with start_span("mt_ja_audio"):
                mt_candidate = translate_candidate_jp_to_en(ja_asr_candidate, cfg)
                _propagate_asr_meta(ja_asr_candidate, mt_candidate)
            _mt_db_id = _reg_store_candidate(
                registry, media_hash, mt_candidate, source="mt",
                model_version=_translation_model_version(mt_candidate, cfg), parent_id=_asr_db_id,
            )
            # Always write raw MT output regardless of whether LLM polish runs.
            raw_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.raw.en.srt"
            write_candidate_srt(mt_candidate, str(raw_srt), cfg)
            logger.info(f"Saved pre-polish translation output: {raw_srt.name}")
            if use_llm_polish:
                with start_span("llm_polish_ja_audio"):
                    polished = polish_candidate_with_llm(mt_candidate, cfg, ja_candidate=ja_asr_candidate)
                    # polish_candidate_with_llm already appends "_llm"; do not re-tag here.
                    candidate = enforce_constraints_on_candidate(polished, cfg)
                polish_stats = _compare_candidates(mt_candidate, candidate)
                _log_polish_stats(polish_stats)
                _final_db_id = _reg_store_candidate(
                    registry, media_hash, candidate, source="mt_llm",
                    model_version=cfg.llm_model_name, parent_id=_mt_db_id,
                )
            else:
                candidate = mt_candidate
                _final_db_id = _mt_db_id
        elif en_audio_order is not None:  # fallback
            strategy = "en_audio_asr"
            logger.info("Fallback: English audio ASR")
            with start_span("extract_en_audio"):
                audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_en_a{en_audio_order}.wav"
                extract_audio_with_ffmpeg(str(video_path), str(audio_path), en_audio_order)
            with start_span("asr_en_audio"):
                asr = FasterWhisperASR(cfg)
                _asr_lang = source_language if source_language != "auto" else "en"
                segments, _ = asr.transcribe_audio_to_segments(str(audio_path), language=_asr_lang)
                candidate = build_candidate_from_segments(
                    segments,
                    cfg,
                    candidate_id=f"en_audio_asr_a{en_audio_order}",
                    language="en",
                    origin_stream=f"audio:{en_audio_order}",
                )
                if _probe_of_en_track_failed:
                    _add_asr_source_warning(
                        candidate,
                        type_="language_probe_failed",
                        detail=(
                            f"Language probe failed for EN-tagged track {en_audio_order}; "
                            "stream metadata language tag was trusted without verification"
                        ),
                    )
            try:
                audio_path.unlink(missing_ok=True)
            except PermissionError:
                logger.debug("Could not delete temp file %s (PermissionError)", audio_path)
            _final_db_id = _reg_store_candidate(
                registry, media_hash, candidate, source="asr",
                model_version=cfg.asr_model_name,
            )
        elif media.audio_streams:
            # Untagged audio fallback. Many WEB-DL / MP4 containers have no
            # ISO-639 language tag on the audio stream, so none of the above
            # branches match. Since this pipeline is built for JP→EN, treat
            # the selected track as Japanese. User can override with
            # --audio-track if there are multiple tracks and the chosen track
            # is wrong.
            if selected_untagged_audio_order is not None:
                # Heuristic was already computed during the language probe step
                # (probe ran but was inconclusive).
                fallback_order = selected_untagged_audio_order
                _fallback_reason = "selected by prior heuristic (language probe inconclusive)"
            else:
                fallback_order, _fallback_reason = _select_untagged_audio_fallback(media)
                selected_untagged_audio_order = fallback_order
            strategy = "untagged_audio_asr_mt"
            _track_count = len(media.audio_streams)
            if _track_count > 1:
                logger.warning(
                    "Ambiguous audio tagging: %d tracks found with no recognized "
                    "language tag. Selected track %d as primary Japanese (%s). "
                    "Use --audio-track N to override.",
                    _track_count, fallback_order, _fallback_reason,
                )
            else:
                logger.warning(
                    "No language-tagged audio found; treating track %d as "
                    "Japanese (%s). Pass --audio-track N to override.",
                    fallback_order, _fallback_reason,
                )
            with start_span("extract_untagged_audio"):
                audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_ja_a{fallback_order}.wav"
                extract_audio_with_ffmpeg(str(video_path), str(audio_path), fallback_order)
            with start_span("asr_untagged_audio"):
                asr = FasterWhisperASR(cfg)
                _asr_lang = source_language if source_language != "auto" else "ja"
                segments, _ = asr.transcribe_audio_to_segments(str(audio_path), language=_asr_lang)
                ja_asr_candidate = build_candidate_from_segments(
                    segments,
                    cfg,
                    candidate_id=f"ja_audio_asr_a{fallback_order}",
                    language=_asr_lang,
                    origin_stream=f"audio:{fallback_order}",
                )
                _add_asr_source_warning(
                    ja_asr_candidate,
                    type_="untagged_audio_fallback",
                    detail=(
                        f"ASR used untagged audio track {fallback_order}; "
                        f"selection reason: {_fallback_reason}"
                    ),
                )
            try:
                audio_path.unlink(missing_ok=True)
            except PermissionError:
                logger.debug("Could not delete temp file %s (PermissionError)", audio_path)
            _asr_db_id = _reg_store_candidate(
                registry, media_hash, ja_asr_candidate, source="asr",
                model_version=cfg.asr_model_name,
            )
            with start_span("mt_untagged_audio"):
                mt_candidate = translate_candidate_jp_to_en(ja_asr_candidate, cfg)
                _propagate_asr_meta(ja_asr_candidate, mt_candidate)
            _mt_db_id = _reg_store_candidate(
                registry, media_hash, mt_candidate, source="mt",
                model_version=_translation_model_version(mt_candidate, cfg), parent_id=_asr_db_id,
            )
            # Always write raw MT output regardless of whether LLM polish runs.
            raw_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.raw.en.srt"
            write_candidate_srt(mt_candidate, str(raw_srt), cfg)
            logger.info(f"Saved pre-polish translation output: {raw_srt.name}")
            if use_llm_polish:
                with start_span("llm_polish_untagged_audio"):
                    polished = polish_candidate_with_llm(mt_candidate, cfg, ja_candidate=ja_asr_candidate)
                    # polish_candidate_with_llm already appends "_llm".
                    candidate = enforce_constraints_on_candidate(polished, cfg)
                polish_stats = _compare_candidates(mt_candidate, candidate)
                _log_polish_stats(polish_stats)
                _final_db_id = _reg_store_candidate(
                    registry, media_hash, candidate, source="mt_llm",
                    model_version=cfg.llm_model_name, parent_id=_mt_db_id,
                )
            else:
                candidate = mt_candidate
                _final_db_id = _mt_db_id
        else:
            raise RuntimeError(
                "No usable source found for English subtitle generation "
                "(file has no audio or subtitle streams)"
            )

        assert candidate is not None, "Generation strategy produced no candidate"

        # Build and log the explainable source-selection report
        selection_report = _build_selection_report(
            strategy=strategy,
            orig_en_sub_idx=orig_en_sub_idx,
            orig_ja_sub_idx=orig_ja_sub_idx,
            orig_en_audio_order=orig_en_audio_order,
            orig_ja_audio_order=orig_ja_audio_order,
            prefer_subtitles=prefer_subtitles,
            prefer_audio_language=prefer_audio_language,
            skip_embedded_en=skip_embedded_en,
            audio_track_override=audio_track_override,
            probed_lang=probed_lang,
            untagged_audio_order=selected_untagged_audio_order,
            source_language=source_language,
            source_language_rerouted_order=source_language_rerouted_order,
        )
        _log_selection_report(selection_report)

        # Write SRT
        out_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.en.srt"
        with start_span("write_final_srt"):
            write_candidate_srt(candidate, str(out_srt), cfg)
        _reg_store_artifact(registry, media_hash, ARTIFACT_TYPE_SRT, out_srt,
                            candidate_db_id=_final_db_id, run_db_id=_run_db_id)

        # Run QC on the written SRT
        with start_span("subtitle_qc"):
            qc_summary = run_qc(
                out_srt,
                candidate=candidate,
                min_duration=cfg.subtitle_min_duration,
                max_duration=cfg.subtitle_max_duration,
                max_cps=cfg.qc_max_cps,
                max_line_chars=cfg.llm_max_chars_per_line,
                max_lines=cfg.llm_max_lines,
            )

        asr_quality = _asr_quality_summary(candidate)
        low_confidence_count = asr_quality.get("low_confidence_segment_count", 0)
        if low_confidence_count:
            logger.warning(
                "ASR uncertainty: %d low-confidence segment(s), status=%s",
                low_confidence_count,
                asr_quality.get("status", "unknown"),
            )

        # Write machine-readable QC summary alongside the SRT
        import json
        qc_path = Path(cfg.get_path("outbox")) / f"{video_path.stem}.en.qc.json"
        qc_path.write_text(json.dumps(qc_summary, indent=2), encoding="utf-8")
        logger.info("QC summary written: %s", qc_path.name)
        _reg_store_artifact(registry, media_hash, ARTIFACT_TYPE_QC_JSON, qc_path,
                            candidate_db_id=_final_db_id, run_db_id=_run_db_id)

        # Score the selected candidate and log an explainable breakdown
        with start_span("score_candidate"):
            candidate_score = score_candidate(strategy, candidate, qc_summary)
        _log_candidate_score(candidate_score)

        # Determine routing decision (PASS / REVIEW / REJECT) based on score
        # and strategy-level review flags from the selection report.
        _policy = PolicyEngine(cfg)
        routing_decision = _policy.route(candidate_score, selection_report)
        if routing_decision["decision"] == "reject":
            logger.error(
                "✗ Routing decision: REJECT — %s",
                "; ".join(routing_decision["reasons"]) or "score too low",
            )
        elif routing_decision["decision"] == "review":
            logger.warning(
                "⚠ Routing decision: REVIEW — %s",
                "; ".join(routing_decision["reasons"]),
            )
        else:
            logger.info("✓ Routing decision: PASS")

        metadata = {
            "video": str(video_path.name),
            "strategy": strategy,
            "candidate_id": candidate.id,
            "segment_count": candidate.segment_count,
            "output_srt": str(out_srt),
            "qc": qc_summary,
            "qc_json": str(qc_path),
            "selection_report": selection_report,
            "candidate_score": candidate_score,
            "routing_decision": routing_decision,
            "asr_quality": asr_quality,
            "asr_low_confidence_segment_count": low_confidence_count,
            "translation_engine": candidate.meta.get("translation_engine"),
            "translation_model": candidate.meta.get("translation_model") or candidate.meta.get("model"),
            "translation_mode": candidate.meta.get("translation_mode"),
            "translation_fallback": candidate.meta.get("translation_fallback", False),
        }
        if polish_stats is not None:
            metadata.update(polish_stats)
        _reg_finish_run(registry, _run_id, status=PIPELINE_STATUS_COMPLETED)
        logger.info(f"✓ Generation complete (strategy={strategy}, segments={candidate.segment_count})")
        metadata["registry_run_id"] = _run_id if _run_db_id is not None else None
    except Exception as _exc:
        _reg_finish_run(
            registry, _run_id,
            status=PIPELINE_STATUS_FAILED,
            error_message=str(_exc),
        )
        raise
    return metadata


__all__ = ["run_generate", "score_candidate"]
