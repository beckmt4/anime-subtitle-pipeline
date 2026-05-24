"""core.mt — machine translation backend abstraction.

Translates a SubtitleCandidate from one language to another.

The abstract ``MTBackend`` interface allows the runtime to swap translation
engines (e.g., MarianMT, DeepL-local, NLLB) without touching pipeline logic.
The source→target language pair is supplied by the caller (language pack or
runtime config); it is never hardcoded here.

Public API
----------
MTBackend                     Abstract base class.
MarianTranslator              Concrete MarianMT implementation
LLMDirectTranslator           Ollama-compatible direct translation backend
                              (both live in root ``mt.py`` during migration).
translate_candidate(…)        Direction-agnostic translation helper.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.subtitles import SubtitleCandidate


class MTBackend(ABC):
    """Abstract interface for all machine translation engine adapters.

    Language direction (source_lang → target_lang) is supplied as parameters,
    never inferred from hardcoded assumptions.
    """

    @abstractmethod
    def translate(
        self,
        candidate: "SubtitleCandidate",
        source_lang: str,
        target_lang: str,
    ) -> "SubtitleCandidate":
        """Translate all segments in *candidate* from source to target language.

        Parameters
        ----------
        candidate:
            Input SubtitleCandidate whose ``segments`` hold the source text.
        source_lang:
            ISO-639-1 code for the source language (e.g. ``"ja"``).
        target_lang:
            ISO-639-1 code for the target language (e.g. ``"en"``).

        Returns
        -------
        SubtitleCandidate
            New candidate with translated segment text.  Original timestamps
            are preserved.  ``candidate.language`` is set to *target_lang*.
        """

    @abstractmethod
    def load(self) -> None:
        """Pre-load model weights into memory."""

    @abstractmethod
    def unload(self) -> None:
        """Release model weights from memory."""

import logging

import time
from typing import Any, Dict, List, Optional

import requests
import torch
from transformers import MarianMTModel, MarianTokenizer

from core.subtitles import Segment as GenericSegment  # SubtitleCandidate already imported above
from config import Config
from core.translation import (
    TranslationMemoryStore,
    build_prompt_glossary_block,
    build_prompt_memory_block,
    load_active_glossary_data,
)
from packs.language.ja_en.cjk_filter import has_cjk_leak

logger = logging.getLogger(__name__)


VALID_TRANSLATION_ENGINES = {"marian", "llm_direct", "hybrid"}
VALID_DIALOGUE_PROFILES = {"default", "live_action_adult"}
VALID_TRANSLATION_WORKFLOWS = {"single_pass", "literal_then_natural"}


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


class InvalidTranslationEngineError(ValueError):
    """Raised when config selects an unsupported translation engine."""


def _translation_config(config: Config) -> Dict[str, Any]:
    def _get(*keys: str, default: Any = None) -> Any:
        getter = getattr(config, "get", None)
        if getter is None:
            return default
        return getter(*keys, default=default)

    settings = {
        "engine": _get("translation", "engine", default="marian"),
        "fallback_engine": _get("translation", "fallback_engine", default="marian"),
        "context_window_segments": _get("translation", "context_window_segments", default=4),
        "mode": _get("translation", "mode", default="accuracy_first"),
        "dialogue_profile": _get("translation", "dialogue_profile", default="default"),
        "preserve_adult_register": bool(
            _get("translation", "preserve_adult_register", default=False)
        ),
        "flag_low_confidence": bool(
            _get("translation", "flag_low_confidence", default=False)
        ),
        "flag_high_risk_content": bool(
            _get("translation", "flag_high_risk_content", default=False)
        ),
        "timeout": _get("translation", "timeout", default=getattr(config, "llm_timeout", 30)),
        "workflow": _get("translation", "workflow", default="single_pass"),
        "save_intermediate": bool(_get("translation", "save_intermediate", default=False)),
        "memory_enabled": bool(_get("translation", "memory", "enabled", default=False)),
        "memory_path": _get("translation", "memory", "path", default=""),
        "memory_max_matches": int(_get("translation", "memory", "max_matches", default=3)),
        "memory_max_entries_in_prompt": int(
            _get("translation", "memory", "max_entries_in_prompt", default=3)
        ),
    }
    domain_pack = getattr(config, "domain_pack", None)
    domain_style_getter = getattr(config, "get_domain_style_config", None)
    domain_style = domain_style_getter() if callable(domain_style_getter) else {}
    if domain_pack == "jav" and isinstance(domain_style, dict):
        if domain_style.get("dialogue_profile"):
            settings["dialogue_profile"] = domain_style["dialogue_profile"]
        for key in (
            "preserve_adult_register",
            "flag_low_confidence",
            "flag_high_risk_content",
        ):
            if key in domain_style:
                settings[key] = bool(domain_style[key])
    settings["dialogue_profile"] = _validate_dialogue_profile(settings["dialogue_profile"])
    profile = settings["dialogue_profile"]
    profile_preset = _get("translation", "profiles", profile, default={})
    if isinstance(profile_preset, dict):
        for key in (
            "engine",
            "fallback_engine",
            "context_window_segments",
            "mode",
            "timeout",
            "workflow",
        ):
            if profile_preset.get(key) is not None:
                settings[key] = profile_preset[key]
        for key in (
            "preserve_adult_register",
            "flag_low_confidence",
            "flag_high_risk_content",
        ):
            if key in profile_preset:
                settings[key] = bool(profile_preset.get(key))
    return settings


def _validate_engine(engine: str) -> str:
    normalized = (engine or "").strip().lower()
    if normalized not in VALID_TRANSLATION_ENGINES:
        valid = ", ".join(sorted(VALID_TRANSLATION_ENGINES))
        raise InvalidTranslationEngineError(
            f"Invalid translation engine {engine!r}; expected one of: {valid}"
        )
    return normalized


def _validate_dialogue_profile(profile: str) -> str:
    normalized = (profile or "").strip().lower() or "default"
    if normalized not in VALID_DIALOGUE_PROFILES:
        valid = ", ".join(sorted(VALID_DIALOGUE_PROFILES))
        logger.warning(
            "Unknown translation dialogue_profile=%r; expected one of: %s. Falling back to 'default'.",
            profile,
            valid,
        )
        return "default"
    return normalized


def _with_translation_meta(
    candidate: SubtitleCandidate,
    *,
    engine: str,
    model: str,
    mode: str,
    dialogue_profile: str,
    preserve_adult_register: bool = False,
    flag_low_confidence: bool = False,
    flag_high_risk_content: bool = False,
    fallback: bool = False,
    fallback_engine: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta = {
        "translation_engine": engine,
        "translation_model": model,
        "translation_mode": mode,
        "translation_dialogue_profile": dialogue_profile,
        "translation_preserve_adult_register": preserve_adult_register,
        "translation_flag_low_confidence": flag_low_confidence,
        "translation_flag_high_risk_content": flag_high_risk_content,
        "translation_fallback": fallback,
        "fallback_engine": fallback_engine,
        "fallback_reason": fallback_reason,
        "source_candidate_id": candidate.id,
        **_copy_asr_candidate_meta(candidate),
    }
    if extra:
        meta.update(extra)
    return meta


class MarianTranslator:
    """
    Japanese to English translator using MarianMT.
    
    This class wraps the Helsinki-NLP opus-mt-ja-en model and provides
    batch translation of subtitle segments.
    """
    
    def __init__(self, config: Config):
        """
        Initialize the MarianMT translator.
        
        Args:
            config: Configuration object with MT settings
        """
        self.config = config
        self.model = None
        self.tokenizer = None
        
        logger.info("Initializing MarianMT translator")
        logger.info(f"  Model: {config.mt_model_name}")
        logger.info(f"  Device: {config.mt_device}")
        logger.info(f"  Batch size: {config.mt_batch_size}")
    
    def load_model(self) -> None:
        """
        Load the MarianMT model and tokenizer.
        
        This is separated from __init__ to allow lazy loading.
        Downloads the model from Hugging Face on first run.
        
        Raises:
            RuntimeError: If model loading fails
        """
        if self.model is not None:
            logger.debug("Model already loaded")
            return
        
        logger.info("Loading MarianMT model (this may download the model on first run)...")
        
        try:
            # Load tokenizer and model
            self.tokenizer = MarianTokenizer.from_pretrained(
                self.config.mt_model_name,
                model_max_length=512
            )
            
            self.model = MarianMTModel.from_pretrained(
                self.config.mt_model_name
            )
            
            # Move to configured device
            device = self.config.mt_device
            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA requested but not available, falling back to CPU")
                device = "cpu"
            
            self.model.to(device)
            self.model.eval()  # Set to evaluation mode
            
            logger.info(f"Model loaded successfully on {device}")
            
        except Exception as e:
            logger.error(f"Failed to load MarianMT model: {e}")
            raise RuntimeError(f"Could not load MarianMT model: {e}") from e
    
    def translate_text(self, text: str) -> str:
        """
        Translate a single Japanese text to English.
        
        Args:
            text: Japanese text to translate
            
        Returns:
            English translation
        """
        if not text.strip():
            return ""
        
        # Ensure model is loaded
        self.load_model()
        
        try:
            # Tokenize input
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512
            )
            
            # Move to device
            device = next(self.model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            # Generate translation
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_length=512,
                    num_beams=4,  # Beam search for better quality
                    early_stopping=True
                )
            
            # Decode output
            translation = self.tokenizer.decode(
                outputs[0],
                skip_special_tokens=True
            )
            
            return translation.strip()
            
        except Exception as e:
            logger.error(f"Translation failed for text: {text[:50]}... Error: {e}")
            return text  # Return original text on error
    
    def translate_batch(self, texts: List[str]) -> List[str]:
        """
        Translate a batch of Japanese texts to English.
        
        More efficient than translating one by one.
        
        Args:
            texts: List of Japanese texts to translate
            
        Returns:
            List of English translations (same order as input)
        """
        if not texts:
            return []
        
        # Filter out empty texts but remember their positions
        non_empty_indices = [i for i, text in enumerate(texts) if text.strip()]
        non_empty_texts = [texts[i] for i in non_empty_indices]
        
        if not non_empty_texts:
            return [""] * len(texts)
        
        # Ensure model is loaded
        self.load_model()
        
        try:
            # Tokenize all inputs
            inputs = self.tokenizer(
                non_empty_texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512
            )
            
            # Move to device
            device = next(self.model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            # Generate translations
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_length=512,
                    num_beams=4,
                    early_stopping=True
                )
            
            # Decode all outputs
            translations = self.tokenizer.batch_decode(
                outputs,
                skip_special_tokens=True
            )
            translations = [t.strip() for t in translations]
            
            # Reconstruct full list with empty strings in original positions
            result = [""] * len(texts)
            for i, idx in enumerate(non_empty_indices):
                result[idx] = translations[i]
            
            return result
            
        except Exception as e:
            logger.error(f"Batch translation failed: {e}")
            # Return original texts on error
            return texts
    
    # ------------------------------------------------------------------
    # New unified data-model API
    # ------------------------------------------------------------------
    def translate_candidate(self, candidate: SubtitleCandidate, target_language: str = "en") -> SubtitleCandidate:
        """Translate a Japanese SubtitleCandidate to target language (default English).

        Preserves timing; returns a NEW candidate whose segments contain the
        translated text as `text`.
        """
        tcfg = _translation_config(self.config)
        if not candidate.segments:
            return SubtitleCandidate(
                id=f"{candidate.id}_mt",
                language=target_language,
                source="mt",
                origin_stream=candidate.origin_stream,
                segments=[],
                meta={
                    "model": self.config.mt_model_name,
                    **_with_translation_meta(
                        candidate,
                        engine="marian",
                        model=self.config.mt_model_name,
                        mode=tcfg["mode"],
                        dialogue_profile=tcfg["dialogue_profile"],
                        preserve_adult_register=tcfg["preserve_adult_register"],
                        flag_low_confidence=tcfg["flag_low_confidence"],
                        flag_high_risk_content=tcfg["flag_high_risk_content"],
                    ),
                },
            )
        # Iterate in mt_batch_size chunks. Previously this passed the entire
        # segment list to translate_batch() as a single call, which caused
        # tokenizer padding to the longest sequence across ALL segments and a
        # single model.generate(num_beams=4) over the full padded tensor. On
        # CPU with ~900 segments this ballooned RAM to ~48 GB and ran for
        # hours. Matches the same batched translation approach used across MT paths.
        batch_size = self.config.mt_batch_size
        total = len(candidate.segments)
        num_batches = (total - 1) // batch_size + 1
        logger.info(
            f"Translating {total} segments (JA → EN) in {num_batches} batches of {batch_size}"
        )
        translations: List[str] = []
        for i in range(0, total, batch_size):
            batch = candidate.segments[i:i + batch_size]
            batch_texts = [s.text for s in batch]
            logger.debug(f"Translating batch {i // batch_size + 1}/{num_batches}")
            translations.extend(self.translate_batch(batch_texts))
        new_segments = [
            GenericSegment(
                start=s.start,
                end=s.end,
                text=t if t else "",
                meta={"source_text_ja": s.text, **dict(s.meta)},
            )
            for s, t in zip(candidate.segments, translations)
        ]
        return SubtitleCandidate(
            id=f"{candidate.id}_mt",
            language=target_language,
            source="mt",
            origin_stream=candidate.origin_stream,
            segments=new_segments,
            meta={
                "model": self.config.mt_model_name,
                **_with_translation_meta(
                    candidate,
                    engine="marian",
                    model=self.config.mt_model_name,
                    mode=tcfg["mode"],
                    dialogue_profile=tcfg["dialogue_profile"],
                    preserve_adult_register=tcfg["preserve_adult_register"],
                    flag_low_confidence=tcfg["flag_low_confidence"],
                    flag_high_risk_content=tcfg["flag_high_risk_content"],
                ),
            },
        )
    
    def unload_model(self) -> None:
        """
        Unload the model to free memory.
        
        Clears model and tokenizer references and empties CUDA cache
        if GPU was used.
        """
        if self.model is not None:
            logger.debug("Unloading MarianMT model")
            self.model = None
            self.tokenizer = None
            torch.cuda.empty_cache()


class LLMDirectTranslator:
    """Direct Japanese-to-English subtitle translator using local Ollama API."""

    def __init__(self, config: Config):
        self.config = config
        tcfg = _translation_config(config)
        self.model_name = config.llm_model_name
        self.base_url = config.llm_base_url.rstrip("/")
        self.mode = tcfg["mode"]
        self.dialogue_profile = tcfg["dialogue_profile"]
        self.preserve_adult_register = bool(tcfg["preserve_adult_register"])
        self.flag_low_confidence = bool(tcfg["flag_low_confidence"])
        self.flag_high_risk_content = bool(tcfg["flag_high_risk_content"])
        self.context_window_segments = int(tcfg["context_window_segments"])
        self.timeout = int(tcfg["timeout"])
        self.glossary_data = load_active_glossary_data(config)
        self.memory_max_matches = max(0, int(tcfg["memory_max_matches"]))
        self.memory_max_entries_in_prompt = max(0, int(tcfg["memory_max_entries_in_prompt"]))
        self.translation_memory = self._init_translation_memory(
            enabled=bool(tcfg["memory_enabled"]),
            configured_path=str(tcfg["memory_path"] or "").strip(),
        )

        logger.info("Initializing LLM direct translator")
        logger.info("  Model: %s", self.model_name)
        logger.info("  Mode: %s", self.mode)
        logger.info("  Dialogue profile: %s", self.dialogue_profile)
        logger.info("  Context window: %d segment(s)", self.context_window_segments)

    def _init_translation_memory(
        self,
        *,
        enabled: bool,
        configured_path: str,
    ) -> Optional[TranslationMemoryStore]:
        if not enabled:
            return None
        try:
            memory_path = configured_path
            if not memory_path:
                memory_path = f"{self.config.get_path('outbox')}/translation_memory.jsonl"
            return TranslationMemoryStore(memory_path)
        except Exception as exc:
            logger.warning("Translation memory disabled due to initialization error: %s", exc)
            return None

    def _memory_prompt_block(self, source_text: str, source_lang: str, target_lang: str) -> str:
        if self.translation_memory is None:
            return ""
        domain_pack = self.glossary_data.get("domain_pack")
        language_pack = self.glossary_data.get("language_pack")
        entries = self.translation_memory.query(
            source_text=source_text,
            source_lang=source_lang,
            target_lang=target_lang,
            domain=domain_pack,
            language_pack=language_pack,
            limit=self.memory_max_matches,
        )
        return build_prompt_memory_block(
            entries,
            max_entries=self.memory_max_entries_in_prompt,
        )

    def _mode_instruction(self) -> str:
        if self.mode == "literal":
            instruction = "Translate literally and preserve all meaning, names, register, and implied subjects."
        elif self.mode == "natural_subtitle":
            instruction = "Translate into concise, natural English subtitle lines while preserving meaning."
        else:
            instruction = (
                "Translate for maximum accuracy first, then make the English subtitle natural. "
                "Do not omit, soften, sanitize, or add meaning."
            )
        if self.dialogue_profile == "live_action_adult" and self.preserve_adult_register:
            instruction += (
                " For live-action/adult dialogue, preserve explicit sexual/profane wording, crude language, "
                "hesitation, fragments, and speaker register. Do not euphemize or sanitize explicit content, "
                "and do not add sexual content that is not present in the Japanese source."
            )
        if self.flag_low_confidence:
            instruction += (
                " If a line is uncertain due to unclear source/context, prefix the output with "
                "'[LOW_CONFIDENCE]' instead of guessing."
            )
        if self.flag_high_risk_content:
            instruction += (
                " If content appears to describe real illegal material involving minors or coercion, "
                "prefix with '[REVIEW_HIGH_RISK]' for manual review and do not normalize the content."
            )
        return instruction

    def _context_for_index(self, candidate: SubtitleCandidate, index: int) -> str:
        radius = max(self.context_window_segments, 0)
        start = max(0, index - radius)
        end = min(len(candidate.segments), index + radius + 1)
        lines = []
        for i in range(start, end):
            marker = ">>" if i == index else "  "
            lines.append(f"{marker} {i + 1}: {candidate.segments[i].text}")
        return "\n".join(lines)

    def _build_prompt(
        self,
        candidate: SubtitleCandidate,
        index: int,
        baseline_text: Optional[str] = None,
        previous_english_text: Optional[str] = None,
    ) -> str:
        source_text = candidate.segments[index].text
        glossary_block = build_prompt_glossary_block(source_text, self.glossary_data)
        memory_block = self._memory_prompt_block(
            source_text,
            source_lang=str(candidate.language or "ja").strip().lower() or "ja",
            target_lang="en",
        )
        baseline_block = (
            f"\nBaseline MarianMT translation:\n{baseline_text}\n"
            if baseline_text is not None
            else ""
        )
        previous_english_block = (
            f"\nPrevious accepted English output:\n{previous_english_text}\n"
            if previous_english_text
            else ""
        )
        return (
            "You are translating Japanese dialogue into English subtitles.\n"
            f"Mode: {self.mode}\n"
            f"Dialogue profile: {self.dialogue_profile}\n"
            f"Instruction: {self._mode_instruction()}\n\n"
            "Context segments. Translate only the line marked with >>.\n"
            f"{self._context_for_index(candidate, index)}\n"
            f"{baseline_block}\n"
            f"{previous_english_block}\n"
            f"{glossary_block}\n\n"
            f"{memory_block}\n\n"
            "Return only the English translation for this one subtitle cue.\n"
            f"Japanese cue:\n{source_text}"
        )

    @staticmethod
    def _extract_translation_text(raw_text: str) -> str:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("LLM direct translation returned empty response")
        text = lines[0]
        if ":" in text:
            label, maybe_translation = text.split(":", 1)
            if label.strip().lower() in {"translation", "english", "output"} and maybe_translation.strip():
                text = maybe_translation.strip()
        return text

    def _generate_text(self, prompt: str, retry_count: int = 2) -> str:
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.llm_temperature,
                "top_p": self.config.get("llm", "top_p", default=0.9),
            },
        }
        last_error: Optional[str] = None
        for attempt in range(retry_count + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                response_data = response.json()
                if not isinstance(response_data, dict) or not isinstance(response_data.get("response"), str):
                    raise RuntimeError("LLM direct translation returned malformed response payload")
                text = self._extract_translation_text(response_data["response"])
                if has_cjk_leak(text):
                    raise RuntimeError("LLM direct translation returned non-English output")
                return text
            except requests.Timeout:
                logger.warning("LLM direct request timeout (attempt %d/%d)", attempt + 1, retry_count + 1)
                last_error = "request timeout"
            except Exception as e:
                logger.warning("LLM direct request failed (attempt %d/%d): %s", attempt + 1, retry_count + 1, e)
                last_error = str(e)
            if attempt < retry_count:
                time.sleep(1)
        if last_error:
            raise RuntimeError(
                f"LLM direct translation failed after {retry_count + 1} attempts: {last_error}"
            )
        raise RuntimeError(f"LLM direct translation failed after {retry_count + 1} attempts")

    def translate_candidate(
        self,
        candidate: SubtitleCandidate,
        target_language: str = "en",
        baseline_candidate: Optional[SubtitleCandidate] = None,
        engine_name: str = "llm_direct",
    ) -> SubtitleCandidate:
        translations: List[str] = []
        for i, segment in enumerate(candidate.segments):
            if not segment.text.strip():
                translations.append("")
                continue
            baseline_text = None
            if baseline_candidate is not None and i < len(baseline_candidate.segments):
                baseline_text = baseline_candidate.segments[i].text
            previous_english_text = next((t for t in reversed(translations) if t.strip()), None)
            prompt = self._build_prompt(
                candidate,
                i,
                baseline_text=baseline_text,
                previous_english_text=previous_english_text,
            )
            translations.append(self._generate_text(prompt))

        new_segments = [
            GenericSegment(
                start=s.start,
                end=s.end,
                text=t,
                meta={"source_text_ja": s.text, **dict(s.meta)},
            )
            for s, t in zip(candidate.segments, translations)
        ]
        extra = {
            "context_window_segments": self.context_window_segments,
            "llm_base_url": self.base_url,
        }
        if baseline_candidate is not None:
            extra.update({
                "baseline_candidate_id": baseline_candidate.id,
                "baseline_engine": baseline_candidate.meta.get("translation_engine", "marian"),
                "baseline_model": baseline_candidate.meta.get("translation_model", baseline_candidate.meta.get("model")),
            })
        return SubtitleCandidate(
            id=f"{candidate.id}_{engine_name}",
            language=target_language,
            source="llm_translate",
            origin_stream=candidate.origin_stream,
            segments=new_segments,
            meta={
                "model": self.model_name,
                **_with_translation_meta(
                    candidate,
                    engine=engine_name,
                    model=self.model_name,
                    mode=self.mode,
                    dialogue_profile=self.dialogue_profile,
                    preserve_adult_register=self.preserve_adult_register,
                    flag_low_confidence=self.flag_low_confidence,
                    flag_high_risk_content=self.flag_high_risk_content,
                    extra=extra,
                ),
            },
        )


def _translate_with_marian(
    candidate: SubtitleCandidate,
    config: Config,
    target_language: str,
) -> SubtitleCandidate:
    translator = MarianTranslator(config)
    try:
        return translator.translate_candidate(candidate, target_language=target_language)
    finally:
        translator.unload_model()


def _fallback_to_marian(
    candidate: SubtitleCandidate,
    config: Config,
    *,
    failed_engine: str,
    reason: Exception,
    target_language: str,
) -> SubtitleCandidate:
    logger.warning(
        "Translation engine %s failed; falling back to MarianMT: %s",
        failed_engine,
        reason,
    )
    fallback = _translate_with_marian(candidate, config, target_language)
    fallback.meta.update({
        "translation_fallback": True,
        "failed_translation_engine": failed_engine,
        "fallback_engine": "marian",
        "fallback_reason": str(reason),
    })
    return fallback


def translate_candidate(
    candidate: SubtitleCandidate,
    config: Config,
    *,
    engine: Optional[str] = None,
    target_language: str = "en",
) -> SubtitleCandidate:
    """Translate a candidate using the configured translation engine selector."""
    tcfg = _translation_config(config)
    selected_engine = _validate_engine(engine or tcfg["engine"])
    fallback_engine = _validate_engine(tcfg["fallback_engine"])

    if selected_engine == "marian":
        return _translate_with_marian(candidate, config, target_language)

    if selected_engine == "llm_direct":
        try:
            return LLMDirectTranslator(config).translate_candidate(
                candidate,
                target_language=target_language,
            )
        except Exception as exc:
            if fallback_engine != "marian":
                raise
            return _fallback_to_marian(
                candidate,
                config,
                failed_engine="llm_direct",
                reason=exc,
                target_language=target_language,
            )

    if selected_engine == "hybrid":
        baseline = _translate_with_marian(candidate, config, target_language)
        try:
            return LLMDirectTranslator(config).translate_candidate(
                candidate,
                target_language=target_language,
                baseline_candidate=baseline,
                engine_name="hybrid",
            )
        except Exception as exc:
            logger.warning("Hybrid LLM refinement failed; returning Marian baseline: %s", exc)
            baseline.meta.update({
                "translation_engine": "hybrid",
                "translation_model": config.llm_model_name,
                "translation_fallback": True,
                "fallback_engine": "marian",
                "fallback_reason": str(exc),
                "baseline_engine": "marian",
                "baseline_model": config.mt_model_name,
            })
            baseline.id = f"{candidate.id}_hybrid_fallback_marian"
            return baseline

    raise AssertionError(f"Unhandled translation engine: {selected_engine}")


def translate_candidate_jp_to_en(
    candidate: SubtitleCandidate,
    config: Config,
    engine: Optional[str] = None,
) -> SubtitleCandidate:
    """Convenience function translating a Japanese candidate to English.

    Uses ``translation.engine`` by default while preserving the legacy function
    name used by existing generate/benchmark call sites.
    """
    return translate_candidate(candidate, config, engine=engine, target_language="en")


def translate_candidate_jp_to_en_workflow(
    candidate: SubtitleCandidate,
    config: Config,
    engine: Optional[str] = None,
    ja_candidate: Optional[SubtitleCandidate] = None,
) -> SubtitleCandidate:
    """Translate JP→EN using the configured translation.workflow selector."""
    workflow = str(_translation_config(config).get("workflow", "single_pass")).strip().lower()
    if workflow not in VALID_TRANSLATION_WORKFLOWS:
        logger.warning(
            "Unknown translation.workflow=%r; expected one of %s. Falling back to single_pass.",
            workflow,
            ", ".join(sorted(VALID_TRANSLATION_WORKFLOWS)),
        )
        workflow = "single_pass"

    if workflow == "literal_then_natural":
        return run_two_pass_translation(
            candidate,
            config,
            ja_candidate=ja_candidate,
            target_language="en",
            engine=engine,
        )

    translated = translate_candidate_jp_to_en(candidate, config, engine=engine)
    translated.meta.setdefault("translation_workflow", "single_pass")
    return translated


def run_two_pass_translation(
    candidate: SubtitleCandidate,
    config: Config,
    ja_candidate: Optional[SubtitleCandidate] = None,
    target_language: str = "en",
    engine: Optional[str] = None,
) -> SubtitleCandidate:
    """Run the literal-first / natural-second two-pass translation workflow.

    Pass 1 — Literal: translates the Japanese candidate to a literal English
        candidate using the configured translation engine.
    Pass 2 — Natural adaptation: adapts the literal candidate into readable
        subtitle text via the LLM, using the Japanese source as additional
        context.  The LLM drift guard reverts any segment whose natural output
        diverges from the literal pass, and emits a per-segment QC warning.

    The literal-pass candidate ID and (optionally) its segment texts are stored
    in the returned candidate's ``meta`` for full traceability.

    Args:
        candidate: Japanese source candidate.
        config: Pipeline configuration.
        ja_candidate: Optional Japanese source candidate for LLM context in
            Pass 2.  Defaults to ``candidate`` when not provided.
        target_language: Target language code (default ``"en"``).

    Returns:
        Final SubtitleCandidate with natural subtitle text, timing preserved
        from the source candidate.

    Raises:
        InvalidTranslationEngineError: If the configured translation engine
            is not supported.
    """
    from core.polish import adapt_candidate_from_literal

    tcfg = _translation_config(config)

    # Pass 1: Literal translation
    literal_candidate = translate_candidate(
        candidate,
        config,
        engine=engine,
        target_language=target_language,
    )
    literal_candidate.meta["translation_pass"] = "literal"

    # Pass 2: Natural adaptation via LLM
    ja_ctx = ja_candidate if ja_candidate is not None else candidate
    final_candidate = adapt_candidate_from_literal(
        literal_candidate,
        config,
        ja_candidate=ja_ctx,
    )

    # Store literal pass information in final candidate metadata
    final_candidate.meta["translation_workflow"] = "literal_then_natural"
    final_candidate.meta["literal_pass_candidate_id"] = literal_candidate.id

    if tcfg["save_intermediate"]:
        final_candidate.meta["literal_pass_segments"] = [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in literal_candidate.segments
        ]

    return final_candidate


__all__ = [
    "InvalidTranslationEngineError",
    "LLMDirectTranslator",
    "MarianTranslator",
    "VALID_TRANSLATION_ENGINES",
    "VALID_TRANSLATION_WORKFLOWS",
    "translate_candidate",
    "translate_candidate_jp_to_en",
    "translate_candidate_jp_to_en_workflow",
    "run_two_pass_translation",
]
