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
import time
from typing import List, Optional

import requests

from asr import Segment  # legacy
from models import Segment as GenericSegment, SubtitleCandidate
from config import Config

logger = logging.getLogger(__name__)


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
        """Enforce max lines and per-line character limits with punctuation-aware wrapping."""
        max_lines = self.config.llm_max_lines
        max_chars = self.config.llm_max_chars_per_line
        if not text:
            return text
        cleaned = ' '.join(text.replace('\r', '').split())  # collapse whitespace
        # Early return if short
        if len(cleaned) <= max_chars and '\n' not in cleaned:
            return cleaned
        import re
        # Split into sentence-like chunks first (.,!,?)
        sentence_chunks = re.split(r'(?<=[.!?])\s+', cleaned)
        refined = []
        for chunk in sentence_chunks:
            if len(chunk) <= max_chars:
                refined.append(chunk)
            else:
                # Further split by comma boundaries while preserving commas
                parts = re.split(r'(,\s*)', chunk)
                assemble = ''
                for part in parts:
                    if not part:
                        continue
                    candidate = (assemble + part).strip()
                    if len(candidate) <= max_chars:
                        assemble = candidate
                    else:
                        if assemble:
                            refined.append(assemble)
                        # If part itself too long, hard-wrap it
                        if len(part) > max_chars:
                            hard = part
                            while len(hard) > max_chars and len(refined) < max_lines:
                                refined.append(hard[:max_chars])
                                hard = hard[max_chars:]
                            if hard and len(refined) < max_lines:
                                assemble = hard.strip()
                            else:
                                assemble = ''
                        else:
                            assemble = part.strip()
                        if len(refined) >= max_lines:
                            break
                if assemble and len(refined) < max_lines:
                    refined.append(assemble)
        # Greedy merge small fragments to use lines efficiently
        lines = []
        current = ''
        for frag in refined:
            if not frag:
                continue
            candidate = (current + ' ' + frag).strip() if current else frag
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = frag
            if len(lines) == max_lines:
                break
        if len(lines) < max_lines and current:
            lines.append(current)
        # Truncation indication
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        remaining_text_len = sum(len(c) for c in sentence_chunks)
        produced_len = sum(len(c) for c in lines)
        if produced_len < remaining_text_len and lines:
            last = lines[-1]
            if len(last) + 1 <= max_chars:
                lines[-1] = last[:max_chars-1] + '…' if len(last) < max_chars else last
        return '\n'.join(lines)
    
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
                # Security: Ensure we're only connecting to localhost
                if not self.base_url.startswith(("http://localhost", "http://127.0.0.1")):
                    logger.warning(f"Non-localhost LLM endpoint: {self.base_url}")
                
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
    
    def polish_segments(
        self,
        segments: List[Segment],
        style: Optional[str] = None
    ) -> List[Segment]:
        """
        Polish all segments in the list.
        
        Updates each segment with text_en_final field containing polished text.
        Processes segments one by one with progress logging.
        
        Args:
            segments: List of Segment objects with text_ja and text_en_raw
            style: Override style for this batch
            
        Returns:
            The same list of segments with text_en_final populated
        """
        if not segments:
            return segments
        
        logger.info(f"Polishing {len(segments)} segments with LLM ({self.style} style)")
        
        # Check connection first
        if not self.check_connection():
            logger.warning("LLM endpoint not accessible, skipping polishing")
            # Fall back to raw translations
            for seg in segments:
                seg.text_en_final = seg.text_en_raw
            return segments
        
        # Process each segment
        for i, seg in enumerate(segments, 1):
            if i % 10 == 0:
                logger.debug(f"Polishing segment {i}/{len(segments)}")
            
            polished = self.polish_text(
                text_ja=seg.text_ja,
                text_en_raw=seg.text_en_raw,
                style=style
            )
            
            seg.text_en_final = polished
        
        logger.info("Polishing complete")
        
        return segments

    # ---------------------------------------------------------------
    # New unified candidate API
    # ---------------------------------------------------------------
    def polish_candidate(
        self,
        candidate: SubtitleCandidate,
        style: Optional[str] = None
    ) -> SubtitleCandidate:
        """Return a new polished SubtitleCandidate.

        Input candidate expected to contain machine-translated English text
        in its segments. Output candidate has same timing with polished text.
        """
        if not candidate.segments:
            return SubtitleCandidate(
                id=f"{candidate.id}_llm",
                language=candidate.language,
                source="mt_llm",
                origin_stream=candidate.origin_stream,
                segments=[],
                meta={"polisher_model": self.model_name},
            )
        # If LLM disabled or unreachable, return pass-through candidate
        if not self.config.llm_enabled or not self.check_connection():
            logger.info("LLM disabled/unreachable; returning pass-through polished candidate")
            passthrough_segments = [
                GenericSegment(s.start, s.end, s.text) for s in candidate.segments
            ]
            return SubtitleCandidate(
                id=f"{candidate.id}_llm",
                language=candidate.language,
                source="mt_llm",
                origin_stream=candidate.origin_stream,
                segments=passthrough_segments,
                meta={"polisher_model": self.model_name, "fallback": True},
            )
        polished_segments: List[GenericSegment] = []
        for s in candidate.segments:
            polished = self.polish_text(text_ja="", text_en_raw=s.text, style=style)  # original JA not available here
            polished_segments.append(GenericSegment(s.start, s.end, polished))
        return SubtitleCandidate(
            id=f"{candidate.id}_llm",
            language=candidate.language,
            source="mt_llm",
            origin_stream=candidate.origin_stream,
            segments=polished_segments,
            meta={"polisher_model": self.model_name},
        )


def polish_english_subtitles_with_llm(
    segments: List[Segment],
    config: Config,
    style: Optional[str] = None
) -> List[Segment]:
    """
    Convenience function for LLM polishing.
    
    If LLM is disabled in config, just copies text_en_raw to text_en_final.
    
    Args:
        segments: List of Segment objects with Japanese and raw English text
        config: Configuration object
        style: Override the configured style
        
    Returns:
        Segments with polished English in text_en_final
    """
    if not config.llm_enabled:
        logger.info("LLM polishing disabled, using raw translations")
        for seg in segments:
            seg.text_en_final = seg.text_en_raw
        return segments
    
    polisher = LLMPolisher(config)
    return polisher.polish_segments(segments, style=style)


def polish_candidate_with_llm(candidate: SubtitleCandidate, config: Config, style: Optional[str] = None) -> SubtitleCandidate:
    polisher = LLMPolisher(config)
    return polisher.polish_candidate(candidate, style=style)


def enforce_subtitle_constraints_on_segments(segments: List[Segment], config: Config) -> int:
    """Re-apply line/char constraints to Segment.text_en_final; returns number of adjustments."""
    polisher = LLMPolisher(config)
    adjustments = 0
    for seg in segments:
        if not seg.text_en_final:
            continue
        adjusted = polisher._enforce_constraints(seg.text_en_final)
        if adjusted != seg.text_en_final:
            seg.text_en_final = adjusted
            adjustments += 1
    if adjustments:
        logger.info(f"Constraint re-validation adjusted {adjustments} segment(s)")
    return adjustments


def enforce_constraints_on_candidate(candidate: SubtitleCandidate, config: Config) -> SubtitleCandidate:
    polisher = LLMPolisher(config)
    new_segments: List[GenericSegment] = []
    changed = 0
    for s in candidate.segments:
        adjusted = polisher._enforce_constraints(s.text)
        if adjusted != s.text:
            changed += 1
        new_segments.append(GenericSegment(s.start, s.end, adjusted))
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


class BatchPolisher:
    """
    Polisher for multiple segment lists with persistent connection.
    
    Usage:
        with BatchPolisher(config) as polisher:
            for segments in segment_batches:
                polisher.polish(segments)
                # process segments...
    """
    
    def __init__(self, config: Config):
        self.polisher = LLMPolisher(config)
        self.enabled = config.llm_enabled
    
    def __enter__(self):
        if self.enabled:
            # Verify connection on enter
            if not self.polisher.check_connection():
                logger.warning("LLM endpoint not accessible, polishing will be skipped")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # No cleanup needed for HTTP client
    
    def polish(self, segments: List[Segment], style: Optional[str] = None) -> List[Segment]:
        """Polish segments."""
        if not self.enabled:
            for seg in segments:
                seg.text_en_final = seg.text_en_raw
            return segments
        
        return self.polisher.polish_segments(segments, style=style)

    def polish_candidate(self, candidate: SubtitleCandidate, style: Optional[str] = None) -> SubtitleCandidate:
        if not self.enabled:
            return SubtitleCandidate(
                id=f"{candidate.id}_llm",
                language=candidate.language,
                source="mt_llm",
                origin_stream=candidate.origin_stream,
                segments=[GenericSegment(s.start, s.end, s.text) for s in candidate.segments],
                meta={"fallback": True},
            )
        return self.polisher.polish_candidate(candidate, style=style)

__all__ = [
    "LLMPolisher",
    "polish_english_subtitles_with_llm",
    "polish_candidate_with_llm",
    "enforce_subtitle_constraints_on_segments",
    "enforce_constraints_on_candidate",
    "BatchPolisher",
]


# Advanced: Batch processing with concurrent requests (optional enhancement)
class ConcurrentPolisher:
    """
    Polisher that processes multiple segments concurrently.
    
    This is an optional enhancement for faster processing with an LLM
    that can handle concurrent requests. Use with caution as it may
    overload the LLM server.
    """
    
    def __init__(self, config: Config, max_concurrent: int = 3):
        """
        Initialize concurrent polisher.
        
        Args:
            config: Configuration object
            max_concurrent: Maximum number of concurrent requests
        """
        self.polisher = LLMPolisher(config)
        self.max_concurrent = max_concurrent
    
    def polish_segments_concurrent(
        self,
        segments: List[Segment],
        style: Optional[str] = None
    ) -> List[Segment]:
        """
        Polish segments with concurrent requests.
        
        Note: This requires the `concurrent.futures` module and may
        overload small LLM servers. Use standard polish_segments() for
        most cases.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        logger.info(f"Polishing {len(segments)} segments with {self.max_concurrent} concurrent workers")
        
        def polish_one(seg: Segment) -> Segment:
            seg.text_en_final = self.polisher.polish_text(
                seg.text_ja,
                seg.text_en_raw,
                style
            )
            return seg
        
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            # Submit all tasks
            futures = {executor.submit(polish_one, seg): seg for seg in segments}
            
            # Wait for completion with progress
            completed = 0
            for future in as_completed(futures):
                completed += 1
                if completed % 10 == 0:
                    logger.debug(f"Completed {completed}/{len(segments)}")
        
        logger.info("Concurrent polishing complete")
        return segments
