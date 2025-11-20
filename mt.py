"""
Machine Translation using Helsinki-NLP MarianMT.

This module handles Japanese to English translation using the
Helsinki-NLP opus-mt-ja-en model via Hugging Face Transformers.

Key features:
- Segment-by-segment translation to avoid truncation
- Batch processing for efficiency
- CPU-based inference to conserve GPU memory for ASR
- Proper handling of Japanese text encoding
"""

import logging
from typing import List

import torch
from transformers import MarianMTModel, MarianTokenizer

from asr import Segment
from config import Config

logger = logging.getLogger(__name__)


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
    
    def translate_segments_ja_to_en(self, segments: List[Segment]) -> List[Segment]:
        """
        Translate Japanese text in segments to English.
        
        Updates each segment with text_en_raw field containing the translation.
        Processes in batches for efficiency.
        
        Args:
            segments: List of Segment objects with text_ja field
            
        Returns:
            The same list of segments with text_en_raw populated
        """
        if not segments:
            return segments
        
        logger.info(f"Translating {len(segments)} segments (JA → EN)")
        
        batch_size = self.config.mt_batch_size
        
        # Process in batches
        for i in range(0, len(segments), batch_size):
            batch = segments[i:i + batch_size]
            batch_texts = [seg.text_ja for seg in batch]
            
            logger.debug(f"Translating batch {i//batch_size + 1}/{(len(segments)-1)//batch_size + 1}")
            
            # Translate batch
            translations = self.translate_batch(batch_texts)
            
            # Update segments
            for seg, translation in zip(batch, translations):
                seg.text_en_raw = translation
        
        logger.info("Translation complete")
        
        return segments
    
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


def translate_segments_ja_to_en(segments: List[Segment], config: Config) -> List[Segment]:
    """
    Convenience function for one-shot translation.
    
    Creates a translator, translates segments, and cleans up.
    
    Args:
        segments: List of Segment objects with Japanese text
        config: Configuration object
        
    Returns:
        Segments with English translations in text_en_raw
    """
    translator = MarianTranslator(config)
    segments = translator.translate_segments_ja_to_en(segments)
    translator.unload_model()
    return segments


# Alternative: Keep model loaded for batch processing
class BatchTranslator:
    """
    Translator that keeps the model loaded for multiple translation runs.
    
    Usage:
        with BatchTranslator(config) as translator:
            for segments in segment_batches:
                translator.translate(segments)
                # process segments...
    """
    
    def __init__(self, config: Config):
        self.translator = MarianTranslator(config)
    
    def __enter__(self):
        self.translator.load_model()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.translator.unload_model()
    
    def translate(self, segments: List[Segment]) -> List[Segment]:
        """Translate segments."""
        return self.translator.translate_segments_ja_to_en(segments)
