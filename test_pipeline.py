"""
Test and validation utilities for the subtitle pipeline.

This script provides functions to test individual components
and validate the complete pipeline.
"""

import logging
from pathlib import Path

from config import Config, set_config
from audio_utils import check_ffmpeg_available, get_audio_tracks
from asr import FasterWhisperASR, Segment
from mt import MarianTranslator
from llm_polish import LLMPolisher
from srt_writer import SRTWriter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_dependencies():
    """Test that all dependencies are available."""
    logger.info("Testing dependencies...")
    
    # Test ffmpeg
    if check_ffmpeg_available():
        logger.info("✓ ffmpeg available")
    else:
        logger.error("✗ ffmpeg not found")
        return False
    
    # Test PyTorch and CUDA
    try:
        import torch
        logger.info(f"✓ PyTorch {torch.__version__}")
        logger.info(f"  CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"  CUDA device: {torch.cuda.get_device_name(0)}")
    except ImportError:
        logger.error("✗ PyTorch not installed")
        return False
    
    # Test Transformers
    try:
        import transformers
        logger.info(f"✓ Transformers {transformers.__version__}")
    except ImportError:
        logger.error("✗ Transformers not installed")
        return False
    
    # Test Faster-Whisper
    try:
        import faster_whisper
        logger.info("✓ Faster-Whisper available")
    except ImportError:
        logger.error("✗ Faster-Whisper not installed")
        return False
    
    # Test YAML
    try:
        import yaml
        logger.info(f"✓ PyYAML available")
    except ImportError:
        logger.error("✗ PyYAML not installed")
        return False
    
    logger.info("\n✓ All dependencies OK!")
    return True


def test_config():
    """Test configuration loading."""
    logger.info("\nTesting configuration...")
    
    try:
        config = Config("config.yaml")
        logger.info(f"✓ Config loaded: {config}")
        logger.info(f"  Profile: {config.profile}")
        logger.info(f"  ASR device: {config.asr_device}")
        logger.info(f"  ASR model: {config.asr_model_name}")
        logger.info(f"  MT model: {config.mt_model_name}")
        logger.info(f"  LLM enabled: {config.llm_enabled}")
        if config.llm_enabled:
            logger.info(f"  LLM model: {config.llm_model_name}")
        return True
    except Exception as e:
        logger.error(f"✗ Config loading failed: {e}")
        return False


def test_video_info(video_path: str):
    """Test video file and show audio track information."""
    logger.info(f"\nTesting video: {video_path}")
    
    video_path = Path(video_path)
    if not video_path.exists():
        logger.error(f"✗ Video file not found: {video_path}")
        return False
    
    try:
        tracks = get_audio_tracks(str(video_path))
        logger.info(f"✓ Video has {len(tracks)} audio track(s):")
        for track in tracks:
            logger.info(f"  {track}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to read video info: {e}")
        return False


def test_asr(config: Config):
    """Test ASR model loading."""
    logger.info("\nTesting ASR model...")
    
    try:
        asr = FasterWhisperASR(config)
        asr.load_model()
        logger.info("✓ ASR model loaded successfully")
        
        # Create a dummy segment
        test_segment = Segment(
            start=0.0,
            end=2.0,
            text_ja="テスト"
        )
        logger.info(f"✓ Segment test: {test_segment}")
        
        asr.unload_model()
        return True
    except Exception as e:
        logger.error(f"✗ ASR test failed: {e}")
        return False


def test_mt(config: Config):
    """Test machine translation model."""
    logger.info("\nTesting MT model...")
    
    try:
        translator = MarianTranslator(config)
        translator.load_model()
        logger.info("✓ MT model loaded successfully")
        
        # Test translation
        test_text = "こんにちは、世界"
        translation = translator.translate_text(test_text)
        logger.info(f"  Test: '{test_text}' → '{translation}'")
        
        translator.unload_model()
        return True
    except Exception as e:
        logger.error(f"✗ MT test failed: {e}")
        return False


def test_llm(config: Config):
    """Test LLM connection."""
    logger.info("\nTesting LLM connection...")
    
    if not config.llm_enabled:
        logger.info("⊘ LLM disabled in config")
        return True
    
    try:
        polisher = LLMPolisher(config)
        if polisher.check_connection():
            logger.info("✓ LLM endpoint accessible")
            
            # Test polishing
            test_ja = "こんにちは"
            test_en = "Hello"
            result = polisher.polish_text(test_ja, test_en)
            logger.info(f"  Test: '{test_en}' → '{result}'")
            return True
        else:
            logger.warning("⚠ LLM endpoint not accessible")
            logger.info("  Make sure Ollama is running: ollama serve")
            return False
    except Exception as e:
        logger.error(f"✗ LLM test failed: {e}")
        return False


def test_srt_writer(config: Config):
    """Test SRT writing."""
    logger.info("\nTesting SRT writer...")
    
    try:
        writer = SRTWriter(config)
        
        # Create test segments
        test_segments = [
            Segment(0.0, 2.5, "こんにちは", "Hello", "Hello!"),
            Segment(2.5, 5.0, "さようなら", "Goodbye", "Goodbye!"),
            Segment(5.0, 8.0, "ありがとう", "Thank you", "Thank you very much!")
        ]
        
        # Test validation
        warnings = writer.validate_segments(test_segments)
        if warnings:
            logger.warning(f"  Found {len(warnings)} validation warnings")
        else:
            logger.info("✓ Segment validation passed")
        
        # Test SRT formatting
        from srt_writer import format_timestamp_srt
        test_time = 90.5
        formatted = format_timestamp_srt(test_time)
        expected = "00:01:30,500"
        if formatted == expected:
            logger.info(f"✓ Timestamp formatting: {test_time}s → {formatted}")
        else:
            logger.error(f"✗ Timestamp formatting incorrect: got {formatted}, expected {expected}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"✗ SRT writer test failed: {e}")
        return False


def run_all_tests(video_path: str = None):
    """Run all tests."""
    logger.info("="*70)
    logger.info("Running Anime Subtitle Pipeline Tests")
    logger.info("="*70)
    
    results = {}
    
    # Test dependencies
    results["dependencies"] = test_dependencies()
    
    # Test config
    if results["dependencies"]:
        results["config"] = test_config()
        
        if results["config"]:
            config = Config("config.yaml")
            set_config(config)
            
            # Test video (if provided)
            if video_path:
                results["video"] = test_video_info(video_path)
            
            # Test components
            results["asr"] = test_asr(config)
            results["mt"] = test_mt(config)
            results["llm"] = test_llm(config)
            results["srt"] = test_srt_writer(config)
    
    # Summary
    logger.info("\n" + "="*70)
    logger.info("Test Summary")
    logger.info("="*70)
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status}: {test_name}")
    
    all_passed = all(results.values())
    
    if all_passed:
        logger.info("\n✓ All tests passed! System is ready.")
    else:
        logger.info("\n⚠ Some tests failed. Please fix the issues above.")
    
    return all_passed


if __name__ == "__main__":
    import sys
    
    # Check if video path provided
    video_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    if video_path:
        logger.info(f"Testing with video: {video_path}\n")
    else:
        logger.info("No video path provided, skipping video tests\n")
        logger.info("Usage: python test_pipeline.py [video_path]\n")
    
    # Run all tests
    success = run_all_tests(video_path)
    
    sys.exit(0 if success else 1)
