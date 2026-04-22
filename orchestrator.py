"""High-level orchestration for the generation flow.

Provides the primary entry point:
- run_generate(media: MediaInfo, cfg: Config, no_llm: bool = False) -> dict

Generation strategy decision tree (default priorities):
1. If prefer_subtitles and English text subtitles exist → use embedded EN
2. Else if English audio exists and preferred language is EN → EN audio ASR
3. Else if Japanese subtitles exist → JP subtitles → MT (→ optional LLM)
4. Else if Japanese audio exists → JP audio ASR → MT (→ optional LLM)
5. Else fallback to any available audio (EN or JP) → appropriate path

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
from tracing import start_span

logger = logging.getLogger(__name__)


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

    logger.info(
        f"Sources detected: en_sub={en_sub_idx} ja_sub={ja_sub_idx} en_audio={en_audio_order} ja_audio={ja_audio_order}"
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
                polished = polish_candidate_with_llm(mt_candidate, cfg)
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
                polished = polish_candidate_with_llm(mt_candidate, cfg)
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
                polished = polish_candidate_with_llm(mt_candidate, cfg)
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

    # Write SRT
    out_srt = Path(cfg.get_path("outbox")) / f"{video_path.stem}.en.srt"
    with start_span("write_final_srt"):
        write_candidate_srt(candidate, str(out_srt), cfg)

    metadata = {
        "video": str(video_path.name),
        "strategy": strategy,
        "candidate_id": candidate.id,
        "segment_count": candidate.segment_count,
        "output_srt": str(out_srt),
    }
    if polish_stats is not None:
        metadata.update(polish_stats)
    logger.info(f"✓ Generation complete (strategy={strategy}, segments={candidate.segment_count})")
    return metadata


__all__ = ["run_generate"]
