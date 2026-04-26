"""
LLM-based subtitle polishing using local Ollama-compatible API.

This module handles the optional polishing step where raw machine-translated
English subtitles are improved by a local LLM to sound more natural while
preserving meaning and timing.

Key features:
- HTTP client for Ollama-compatible API endpoints
- Configurable natural vs literal translation styles
- Enforces subtitle formatting constraints (line count, character limits)
- Batch processing with error handling
- Retry logic for transient failures
"""

import logging
import re
import time
from typing import List, NamedTuple, Optional

import requests

from models import Segment as GenericSegment, SubtitleCandidate
from config import Config
from subtitle_corrector import check_drift

logger = logging.getLogger(__name__)


_PROPAGATED_ASR_META_KEYS = (
    "asr_quality",
    "asr_quality_status",
    "asr_low_confidence_segment_count",
    "asr_source_warnings",
)


def _copy_asr_candidate_meta(candidate: SubtitleCandidate) -> dict:
    return {
        key: candidate.meta[key]
        for key in _PROPAGATED_ASR_META_KEYS
        if key in candidate.meta
    }

# qwen2.5:7b occasionally emits Chinese (rarely Korean/Japanese) characters
# mixed into English output (~0.5% of segments on VHD Bloodlust 2026-04-20,
# e.g. "Don't push me." → "Don't逼我！（Don't push me.)").
#
# Detection regex: covers all CJK blocks we care about, including full-width
# punctuation (U+FF00-U+FFEF) which the old regex missed (e.g. ，？！（）).
#
# Remediation strategy (strip-before-reject):
#   1. Detect any CJK character in the polished text.
#   2. Strip all CJK characters and collapse whitespace.
#   3. If the stripped result retains at least 1/3 of the raw-MT length and
#      at least 4 chars, use the stripped text (preserves polish improvements
#      for the Latin portion).
#   4. Otherwise fall back to raw MT entirely.
#
# This handles the common pattern where the model appends a Chinese
# parenthetical or explanation after an otherwise good English translation.
_CJK_RE = re.compile(
    r'['
    r'\u2e80-\u2eff'   # CJK Radicals Supplement
    r'\u3000-\u9fff'   # CJK Symbols & Punctuation, Hiragana, Katakana,
                       # CJK Unified Ideographs (4E00-9FFF), and surrounding blocks
    r'\uac00-\ud7af'   # Hangul Syllables
    r'\uf900-\ufaff'   # CJK Compatibility Ideographs
    r'\ufe30-\ufe4f'   # CJK Compatibility Forms
    r'\uff00-\uffef'   # Halfwidth and Fullwidth Forms (catches ，？！（）etc.)
    r']'
)

_SENTENCE_END_RE = re.compile(r'[.!?…]$')

# Stock phrases that the LLM occasionally collapses unrelated lines into.
# If ALL polished outputs in a batch match one of these generic replies the
# entire batch is flagged as a "stock-phrase collapse" and reverted.
_STOCK_PHRASES = frozenset({
    "sure thing.",
    "sure thing",
    "got it.",
    "got it",
    "here you go.",
    "here you go",
    "oh my god!",
    "oh my god",
    "okay.",
    "okay",
    "alright.",
    "alright",
})


class PolishStats(NamedTuple):
    """Counters returned by per-segment LLM polishing runs."""
    total: int
    polished: int       # accepted polished output (different from raw, not reverted)
    reverted: int       # drift-flagged, reverted to raw
    unchanged: int      # identical to raw (LLM made no change)


def _is_stock_phrase_collapse(raw_texts: List[str], polished_texts: List[str]) -> bool:
    """Return True when distinct raw lines all collapsed to the same stock phrase.

    Collapse is declared when:
    - There are at least 2 segments, AND
    - All polished outputs are identical, AND
    - That output (lower-cased, stripped) is a known stock phrase, AND
    - The raw inputs are not all identical (i.e. the LLM introduced collapse).
    """
    if len(polished_texts) < 2:
        return False
    unique_polished = {p.strip().lower() for p in polished_texts}
    if len(unique_polished) != 1:
        return False  # outputs differ — no collapse
    collapsed_phrase = next(iter(unique_polished))
    if collapsed_phrase not in _STOCK_PHRASES:
        return False  # not a known filler phrase
    unique_raw = {r.strip().lower() for r in raw_texts}
    return len(unique_raw) > 1  # raw inputs were diverse → collapse is bad


def _recover_leading_english(polished: str) -> Optional[str]:
    """Attempt to salvage the clean English prefix before the first CJK run.

    Returns the prefix if it looks like complete, usable output; else None.

    Strategy: the model often produces good English then appends a Chinese
    parenthetical or explanation (e.g. "You've got to be kidding me.三次元…").
    We can recover the English portion cleanly.  If CJK appears too early in
    the string (interspersed rather than appended) the prefix will be too short
    or look like a fragment, and we fall back to raw MT instead.

    Acceptance criteria (all must pass):
      - CJK starts after ≥ 40% of the string length (suffix, not interspersed).
      - Leading portion has ≥ 2 words.
      - Leading portion ends with sentence-final punctuation (.!?…) OR has ≥ 4
        words (handles cases without explicit terminal punctuation).
    """
    match = _CJK_RE.search(polished)
    if not match:
        return None
    leading = polished[:match.start()].strip()
    if not leading:
        return None
    if match.start() < len(polished) * 0.4:
        return None  # CJK too early — interspersed, not an appendage
    words = leading.split()
    if len(words) < 2:
        return None
    if not (_SENTENCE_END_RE.search(leading) or len(words) >= 4):
        return None  # fragment (e.g. "Why are you")
    return leading


class LLMPolisher:
    """
    LLM-based subtitle polisher using Ollama-compatible API.
    
    This class sends segments to a local LLM to improve the English translation
    while maintaining timing and meaning constraints.
    """
    
    def __init__(self, config: Config):
        """
        Initialize the LLM polisher.
        
        Args:
            config: Configuration object with LLM settings
        """
        self.config = config
        self.base_url = config.llm_base_url.rstrip('/')
        self.model_name = config.llm_model_name
        self.style = config.llm_style
        self.timeout = config.llm_timeout
        
        logger.info("Initializing LLM polisher")
        logger.info(f"  Endpoint: {self.base_url}")
        logger.info(f"  Model: {self.model_name}")
        logger.info(f"  Style: {self.style}")
    
    def check_connection(self) -> bool:
        """
        Check if the LLM endpoint is accessible.
        
        Sends a GET request to the /api/tags endpoint to verify
        the Ollama server is running and responsive.
        
        Returns:
            True if endpoint responds with 200 status, False otherwise
        """
        try:
            # Try to list models to verify connection
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"LLM endpoint not accessible: {e}")
            return False

    def _enforce_constraints(self, text: str) -> str:
        """Normalize whitespace only; line/char wrapping is delegated to srt_writer.

        Historical note (2026-04-20): this method previously performed aggressive
        punctuation-aware wrapping with a hard character-based truncation path
        (see lines 107-118 of the prior version) that silently dropped overflow
        past (max_lines * max_chars), producing outputs like "full moo" from
        "full moon." The wrapping was also redundant with
        srt_writer.split_into_lines, which already word-wraps cleanly at
        max_chars_per_line boundaries. The original implementation is preserved
        in git history; revert via `git log -p llm_polish.py` if needed.
        """
        if not text:
            return text
        # Collapse whitespace (including stray newlines from MT output) into
        # single spaces. srt_writer will handle line splitting downstream.
        return ' '.join(text.replace('\r', '').split())

    def polish_text(
        self,
        text_ja: str,
        text_en_raw: str,
        style: Optional[str] = None,
        retry_count: int = 2
    ) -> str:
        """
        Polish a single English subtitle using the LLM.
        
        Args:
            text_ja: Original Japanese text (for context)
            text_en_raw: Raw machine-translated English
            style: Override style ("natural" or "literal")
            retry_count: Number of retries on failure
            
        Returns:
            Polished English text, or original text_en_raw on failure
        """
        style = style or self.style
        system_prompt = self.config.get_llm_prompt(style)
        
        # Construct user prompt
        user_prompt = f"""Japanese: {text_ja}
Machine Translation: {text_en_raw}

Improve the English subtitle:"""
        
        # Prepare request payload for Ollama API
        payload = {
            "model": self.model_name,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": self.config.llm_temperature,
                "top_p": self.config.get("llm", "top_p", default=0.9),
            }
        }
        
        # Try with retries
        for attempt in range(retry_count + 1):
            try:
                # Note: non-localhost endpoints (e.g. Unraid Ollama) are valid
                # for production deployments; no warning needed here.
                
                response = requests.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    polished = result.get("response", "").strip()

                    # Basic validation
                    if polished:
                        polished = self._enforce_constraints(polished)
                        # CJK leak guard — qwen2.5:7b sometimes emits Chinese
                        # (or rarely Korean/Japanese) characters mixed into an
                        # otherwise good English translation.
                        if _CJK_RE.search(polished):
                            recovered = _recover_leading_english(polished)
                            if recovered:
                                logger.warning(
                                    f"LLM polish emitted CJK suffix; recovered "
                                    f"English prefix. Before: {polished[:80]!r} "
                                    f"→ After: {recovered[:80]!r}"
                                )
                                return recovered
                            logger.warning(
                                f"LLM polish emitted CJK (could not recover "
                                f"English prefix); falling back to raw MT. "
                                f"Output was: {polished[:100]!r}"
                            )
                            return text_en_raw
                        return polished
                    logger.warning("LLM returned empty response")
                    return text_en_raw
                else:
                    logger.warning(f"LLM API returned status {response.status_code}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"LLM request timeout (attempt {attempt + 1}/{retry_count + 1})")
            except (requests.RequestException, ValueError, KeyError) as e:
                logger.warning(f"LLM request failed (attempt {attempt + 1}/{retry_count + 1}): {e}")
            
            # Wait before retry
            if attempt < retry_count:
                time.sleep(1)
        
        # All retries failed, return original
        logger.warning("All LLM retry attempts failed, using raw translation")
        return text_en_raw

    # ---------------------------------------------------------------
    # Candidate API
    # ---------------------------------------------------------------
    def polish_candidate(
        self,
        candidate: SubtitleCandidate,
        ja_candidate: Optional[SubtitleCandidate] = None,
        style: Optional[str] = None,
    ) -> SubtitleCandidate:
        """Return a new polished SubtitleCandidate.

        Input candidate expected to contain machine-translated English text
        in its segments. Output candidate has same timing with polished text.

        Per-segment drift detection (noun change / length ratio) reverts any
        segment whose polished text drifts from the raw MT. A stock-phrase
        collapse guard reverts all segments when the LLM collapses diverse
        inputs into a single generic filler phrase.

        Args:
            candidate: MT English candidate to polish.
            ja_candidate: Optional matching Japanese source candidate. When
                provided and the segment counts align, the original Japanese
                text is passed to the LLM as context for each segment,
                significantly reducing hallucination and drift.
            style: Override configured LLM style for this run.
        """
        if not candidate.segments:
            return SubtitleCandidate(
                id=f"{candidate.id}_llm",
                language=candidate.language,
                source="mt_llm",
                origin_stream=candidate.origin_stream,
                segments=[],
                meta={"polisher_model": self.model_name, **_copy_asr_candidate_meta(candidate)},
            )
        # If LLM disabled or unreachable, return pass-through candidate
        if not self.config.llm_enabled or not self.check_connection():
            logger.info("LLM disabled/unreachable; returning pass-through polished candidate")
            passthrough_segments = [
                GenericSegment(s.start, s.end, s.text, meta=dict(s.meta)) for s in candidate.segments
            ]
            return SubtitleCandidate(
                id=f"{candidate.id}_llm",
                language=candidate.language,
                source="mt_llm",
                origin_stream=candidate.origin_stream,
                segments=passthrough_segments,
                meta={
                    "polisher_model": self.model_name,
                    "fallback": True,
                    **_copy_asr_candidate_meta(candidate),
                },
            )

        # Build per-segment (text_ja, text_en_raw) pairs. Use the Japanese
        # source candidate when the segment counts match; otherwise fall back
        # to empty Japanese context.
        ja_texts: List[str] = []
        if (
            ja_candidate is not None
            and len(ja_candidate.segments) == len(candidate.segments)
        ):
            ja_texts = [s.text for s in ja_candidate.segments]
            logger.debug(
                "polish_candidate: using %d Japanese source segments for context",
                len(ja_texts),
            )
        else:
            if ja_candidate is not None:
                logger.warning(
                    "polish_candidate: ja_candidate segment count (%d) != "
                    "en_candidate segment count (%d); ignoring Japanese context",
                    len(ja_candidate.segments),
                    len(candidate.segments),
                )
            ja_texts = [""] * len(candidate.segments)

        raw_texts: List[str] = [s.text for s in candidate.segments]
        candidate_texts: List[str] = []

        for s, text_ja in zip(candidate.segments, ja_texts):
            polished = self.polish_text(text_ja=text_ja, text_en_raw=s.text, style=style)
            candidate_texts.append(polished)

        # Stock-phrase collapse guard.
        if _is_stock_phrase_collapse(raw_texts, candidate_texts):
            logger.warning(
                "LLM polish: stock-phrase collapse detected across %d segments "
                "(%r); reverting all to raw MT.",
                len(candidate.segments),
                candidate_texts[0] if candidate_texts else "",
            )
            n_polished, n_reverted, n_unchanged = 0, len(candidate.segments), 0
            polished_segments = [
                GenericSegment(s.start, s.end, s.text, meta=dict(s.meta)) for s in candidate.segments
            ]
            stats = PolishStats(
                total=len(candidate.segments),
                polished=n_polished,
                reverted=n_reverted,
                unchanged=n_unchanged,
            )
            logger.info(
                "[llm_polish] polish_candidate %s: total=%d polished=%d reverted=%d unchanged=%d",
                candidate.id, stats.total, stats.polished, stats.reverted, stats.unchanged,
            )
            return SubtitleCandidate(
                id=f"{candidate.id}_llm",
                language=candidate.language,
                source="mt_llm",
                origin_stream=candidate.origin_stream,
                segments=polished_segments,
                meta={
                    "polisher_model": self.model_name,
                    "polish_stats": stats._asdict(),
                    **_copy_asr_candidate_meta(candidate),
                },
            )

        # Per-segment drift check.
        n_polished = 0
        n_reverted = 0
        n_unchanged = 0
        polished_segments = []
        for s, polished in zip(candidate.segments, candidate_texts):
            is_drift, reason, detail = check_drift(s.text, polished)
            if is_drift:
                logger.debug(
                    "LLM polish drift reverted (reason=%s detail=%s): %r → %r",
                    reason, detail, s.text, polished,
                )
                polished_segments.append(GenericSegment(s.start, s.end, s.text, meta=dict(s.meta)))
                n_reverted += 1
            elif polished == s.text:
                polished_segments.append(GenericSegment(s.start, s.end, polished, meta=dict(s.meta)))
                n_unchanged += 1
            else:
                polished_segments.append(GenericSegment(s.start, s.end, polished, meta=dict(s.meta)))
                n_polished += 1

        stats = PolishStats(
            total=len(candidate.segments),
            polished=n_polished,
            reverted=n_reverted,
            unchanged=n_unchanged,
        )
        logger.info(
            "[llm_polish] polish_candidate %s: total=%d polished=%d reverted=%d unchanged=%d",
            candidate.id, stats.total, stats.polished, stats.reverted, stats.unchanged,
        )
        return SubtitleCandidate(
            id=f"{candidate.id}_llm",
            language=candidate.language,
            source="mt_llm",
            origin_stream=candidate.origin_stream,
            segments=polished_segments,
            meta={
                "polisher_model": self.model_name,
                "polish_stats": stats._asdict(),
                **_copy_asr_candidate_meta(candidate),
            },
        )


def polish_candidate_with_llm(
    candidate: SubtitleCandidate,
    config: Config,
    ja_candidate: Optional[SubtitleCandidate] = None,
    style: Optional[str] = None,
) -> SubtitleCandidate:
    """Convenience wrapper: polish a single MT candidate using the LLM.

    Args:
        candidate: MT English candidate to polish.
        config: Pipeline configuration.
        ja_candidate: Optional matching Japanese source candidate. When provided
            and the segment counts align, the original Japanese text is forwarded
            as context to the LLM, reducing hallucination and semantic drift.
        style: Override configured LLM style.
    """
    polisher = LLMPolisher(config)
    return polisher.polish_candidate(candidate, ja_candidate=ja_candidate, style=style)


def enforce_constraints_on_candidate(candidate: SubtitleCandidate, config: Config) -> SubtitleCandidate:
    polisher = LLMPolisher(config)
    new_segments: List[GenericSegment] = []
    changed = 0
    for s in candidate.segments:
        adjusted = polisher._enforce_constraints(s.text)
        if adjusted != s.text:
            changed += 1
        new_segments.append(GenericSegment(s.start, s.end, adjusted, meta=dict(s.meta)))
    if changed:
        logger.info(f"Constraint enforcement adjusted {changed} segment(s) in candidate {candidate.id}")
    return SubtitleCandidate(
        id=candidate.id,
        language=candidate.language,
        source=candidate.source,
        origin_stream=candidate.origin_stream,
        segments=new_segments,
        meta={**candidate.meta, "constraints_enforced": True},
    )


__all__ = [
    "LLMPolisher",
    "PolishStats",
    "polish_candidate_with_llm",
    "enforce_constraints_on_candidate",
]
