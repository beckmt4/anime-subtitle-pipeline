"""High-level orchestration for the generation flow.

Provides the primary entry point:
- run_generate(media: MediaInfo, cfg: Config, no_llm: bool = False) -> dict

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

Returned metadata includes chosen strategy and output SRT path.
"""
from __future__ import annotations

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

logger = logging.getLogger(__name__)


# Audio language probe settings (used when metadata tag is absent or suspect).
_PROBE_DURATION_SEC = 30       # seconds of audio to sample
_PROBE_JA_THRESHOLD = 0.85    # minimum Whisper confidence to reroute

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
        decision (e.g. ["skip_embedded_en", "audio_track_override=2"])
      - review_recommended: True when the strategy involves a lossy processing
        step (MT / untagged-audio fallback) and human review is advisable
      - review_reason: human-readable justification (None when not recommended)
    """
    overrides_active = []
    sources_evaluated = []

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
        en_audio_detected = orig_en_audio_order is not None
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
        elif strategy == "en_audio_asr" and prefer_audio_language == "en":
            en_audio_status = "selected"
            en_audio_reason = (
                f"English audio track {orig_en_audio_order} selected; "
                "prefer_audio_language=en in config"
            )
        elif strategy == "en_audio_asr":
            en_audio_status = "selected"
            en_audio_reason = (
                f"Fallback: English audio track {orig_en_audio_order} selected "
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
            "stream": f"audio:{orig_en_audio_order}" if en_audio_detected else None,
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
        # The effective JA audio order may have been promoted from the
        # EN-tagged track if the language probe detected Japanese content.
        if probe_rerouted:
            effective_ja_audio = orig_en_audio_order
            probe_rerouted = True
        else:
            effective_ja_audio = orig_ja_audio_order
            probe_rerouted = False
        ja_audio_detected = effective_ja_audio is not None
        if not ja_audio_detected:
            ja_audio_status = "not_available"
            ja_audio_reason = "No Japanese audio stream detected in container"
        elif strategy == "ja_audio_asr_mt":
            ja_audio_status = "selected"
            if probe_rerouted:
                ja_audio_reason = (
                    f"EN-tagged audio track {effective_ja_audio} rerouted by "
                    f"language probe (detected Japanese, confidence ≥ "
                    f"{_PROBE_JA_THRESHOLD:.0%}); processed via ASR → MT → English"
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
            sources_evaluated.append({
                "source": "untagged_audio_asr_mt",
                "stream": "audio:0",
                "detected": True,
                "status": "selected",
                "reason": (
                    "Last-resort fallback: no language-tagged streams found; "
                    "first audio track treated as Japanese and routed via ASR → MT"
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
        if probe_rerouted:
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
        logger.warning("Language probe failed: %s — proceeding with metadata tag", exc)
        return None
    finally:
        probe_path.unlink(missing_ok=True)


def run_generate(
    media: MediaInfo,
    cfg: Config,
    no_llm: bool = False,
    audio_track_override: int | None = None,
    skip_embedded_en: bool = False,
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
        skip_embedded_en: When True, ignore any embedded English subtitle tracks and
            force the pipeline through ASR → MT (→ LLM). Used with --extract-en-subs
            so the extracted embedded subs and the freshly generated subs can be
            compared or used for training.

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

    logger.info(
        f"Sources detected: en_sub={en_sub_idx} ja_sub={ja_sub_idx} en_audio={en_audio_order} ja_audio={ja_audio_order}"
    )

    # When auto-routing and the only audio found is EN-tagged (no JA track),
    # probe the actual audio content so mislabeled Japanese files are routed
    # through the JA ASR → MT path instead of being silently transcribed as
    # English gibberish.
    if (
        audio_track_override is None
        and prefer_audio_language == "auto"
        and ja_audio_order is None
        and en_audio_order is not None
    ):
        probed_lang = _probe_audio_language(video_path, en_audio_order, cfg)
        if probed_lang == "ja":
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

    strategy = None
    candidate: SubtitleCandidate | None = None
    polish_stats: Dict[str, Any] | None = None

    # Decision tree
    if prefer_subtitles and en_sub_idx is not None:
        strategy = "embedded_en"
        logger.info("Strategy: Use embedded English subtitles")
        with start_span("extract_embedded_en"):
            candidate = extract_subtitle_track(video_path, en_sub_idx, language="en",
                                               output_dir=Path(cfg.get_path("temp")))
    elif prefer_audio_language == "en" and en_audio_order is not None:
        strategy = "en_audio_asr"
        logger.info("Strategy: English audio ASR")
        with start_span("extract_en_audio"):
            audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_en_a{en_audio_order}.wav"
            extract_audio_with_ffmpeg(str(video_path), str(audio_path), en_audio_order)
        with start_span("asr_en_audio"):
            asr = FasterWhisperASR(cfg)
            segments = asr.transcribe_audio_to_segments(str(audio_path), language="en")
            candidate = build_candidate_from_segments(
                segments,
                cfg,
                candidate_id=f"en_audio_asr_a{en_audio_order}",
                language="en",
                origin_stream=f"audio:{en_audio_order}",
            )
        audio_path.unlink(missing_ok=True)
    elif ja_sub_idx is not None:
        strategy = "embedded_jp_mt"
        logger.info("Strategy: Japanese subtitles → MT → EN")
        with start_span("extract_embedded_jp"):
            ja_candidate = extract_subtitle_track(video_path, ja_sub_idx, language="ja",
                                                  output_dir=Path(cfg.get_path("temp")))
        with start_span("mt_embedded_jp"):
            mt_candidate = translate_candidate_jp_to_en(ja_candidate, cfg)
        # Always write raw MT output regardless of whether LLM polish runs.
        raw_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.raw.en.srt"
        write_candidate_srt(mt_candidate, str(raw_srt), cfg)
        logger.info(f"Saved pre-polish raw MT: {raw_srt.name}")
        if use_llm_polish:
            with start_span("llm_polish_embedded_jp"):
                polished = polish_candidate_with_llm(mt_candidate, cfg, ja_candidate=ja_candidate)
                # polish_candidate_with_llm already appends "_llm"; do not re-tag here.
                candidate = enforce_constraints_on_candidate(polished, cfg)
            polish_stats = _compare_candidates(mt_candidate, candidate)
            _log_polish_stats(polish_stats)
        else:
            candidate = mt_candidate
    elif (prefer_audio_language in ["ja", "auto"] and ja_audio_order is not None):
        strategy = "ja_audio_asr_mt"
        logger.info("Strategy: Japanese audio → ASR → MT → EN")
        with start_span("extract_ja_audio"):
            audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_ja_a{ja_audio_order}.wav"
            extract_audio_with_ffmpeg(str(video_path), str(audio_path), ja_audio_order)
        with start_span("asr_ja_audio"):
            asr = FasterWhisperASR(cfg)
            segments = asr.transcribe_audio_to_segments(str(audio_path), language="ja")
            ja_asr_candidate = build_candidate_from_segments(
                segments,
                cfg,
                candidate_id=f"ja_audio_asr_a{ja_audio_order}",
                language="ja",
                origin_stream=f"audio:{ja_audio_order}",
            )
        audio_path.unlink(missing_ok=True)
        with start_span("mt_ja_audio"):
            mt_candidate = translate_candidate_jp_to_en(ja_asr_candidate, cfg)
        # Always write raw MT output regardless of whether LLM polish runs.
        raw_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.raw.en.srt"
        write_candidate_srt(mt_candidate, str(raw_srt), cfg)
        logger.info(f"Saved pre-polish raw MT: {raw_srt.name}")
        if use_llm_polish:
            with start_span("llm_polish_ja_audio"):
                polished = polish_candidate_with_llm(mt_candidate, cfg, ja_candidate=ja_asr_candidate)
                # polish_candidate_with_llm already appends "_llm"; do not re-tag here.
                candidate = enforce_constraints_on_candidate(polished, cfg)
            polish_stats = _compare_candidates(mt_candidate, candidate)
            _log_polish_stats(polish_stats)
        else:
            candidate = mt_candidate
    elif en_audio_order is not None:  # fallback
        strategy = "en_audio_asr"
        logger.info("Fallback: English audio ASR")
        with start_span("extract_en_audio"):
            audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_en_a{en_audio_order}.wav"
            extract_audio_with_ffmpeg(str(video_path), str(audio_path), en_audio_order)
        with start_span("asr_en_audio"):
            asr = FasterWhisperASR(cfg)
            segments = asr.transcribe_audio_to_segments(str(audio_path), language="en")
            candidate = build_candidate_from_segments(
                segments,
                cfg,
                candidate_id=f"en_audio_asr_a{en_audio_order}",
                language="en",
                origin_stream=f"audio:{en_audio_order}",
            )
        audio_path.unlink(missing_ok=True)
    elif media.audio_streams:
        # Untagged audio fallback. Many WEB-DL / MP4 containers have no
        # ISO-639 language tag on the audio stream, so none of the above
        # branches match. Since this pipeline is built for JP→EN, treat
        # the first audio track as Japanese. User can override with
        # --audio-track if there are multiple tracks and track 0 is wrong.
        fallback_order = 0
        strategy = "untagged_audio_asr_mt"
        logger.warning(
            f"No language-tagged audio found; falling back to audio track "
            f"{fallback_order} as Japanese. Pass --audio-track N to override."
        )
        with start_span("extract_untagged_audio"):
            audio_path = Path(cfg.get_path("temp")) / f"{video_path.stem}_ja_a{fallback_order}.wav"
            extract_audio_with_ffmpeg(str(video_path), str(audio_path), fallback_order)
        with start_span("asr_untagged_audio"):
            asr = FasterWhisperASR(cfg)
            segments = asr.transcribe_audio_to_segments(str(audio_path), language="ja")
            ja_asr_candidate = build_candidate_from_segments(
                segments,
                cfg,
                candidate_id=f"ja_audio_asr_a{fallback_order}",
                language="ja",
                origin_stream=f"audio:{fallback_order}",
            )
        audio_path.unlink(missing_ok=True)
        with start_span("mt_untagged_audio"):
            mt_candidate = translate_candidate_jp_to_en(ja_asr_candidate, cfg)
        # Always write raw MT output regardless of whether LLM polish runs.
        raw_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.raw.en.srt"
        write_candidate_srt(mt_candidate, str(raw_srt), cfg)
        logger.info(f"Saved pre-polish raw MT: {raw_srt.name}")
        if use_llm_polish:
            with start_span("llm_polish_untagged_audio"):
                polished = polish_candidate_with_llm(mt_candidate, cfg, ja_candidate=ja_asr_candidate)
                # polish_candidate_with_llm already appends "_llm".
                candidate = enforce_constraints_on_candidate(polished, cfg)
            polish_stats = _compare_candidates(mt_candidate, candidate)
            _log_polish_stats(polish_stats)
        else:
            candidate = mt_candidate
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
    )
    _log_selection_report(selection_report)

    # Write SRT
    out_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.en.srt"
    with start_span("write_final_srt"):
        write_candidate_srt(candidate, str(out_srt), cfg)

    # Run QC on the written SRT
    with start_span("subtitle_qc"):
        qc_summary = run_qc(
            out_srt,
            min_duration=cfg.subtitle_min_duration,
            max_duration=cfg.subtitle_max_duration,
            max_cps=cfg.qc_max_cps,
            max_line_chars=cfg.llm_max_chars_per_line,
            max_lines=cfg.llm_max_lines,
        )

    # Write machine-readable QC summary alongside the SRT
    import json
    qc_path = Path(cfg.get_path("outbox")) / f"{video_path.stem}.en.qc.json"
    qc_path.write_text(json.dumps(qc_summary, indent=2), encoding="utf-8")
    logger.info("QC summary written: %s", qc_path.name)

    metadata = {
        "video": str(video_path.name),
        "strategy": strategy,
        "candidate_id": candidate.id,
        "segment_count": candidate.segment_count,
        "output_srt": str(out_srt),
        "qc": qc_summary,
        "qc_json": str(qc_path),
        "selection_report": selection_report,
    }
    if polish_stats is not None:
        metadata.update(polish_stats)
    logger.info(f"✓ Generation complete (strategy={strategy}, segments={candidate.segment_count})")
    return metadata


__all__ = ["run_generate"]
