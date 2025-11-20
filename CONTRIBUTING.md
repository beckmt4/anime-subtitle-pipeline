# Contributing Guide

## Code Style and Best Practices

This document outlines the coding standards and best practices for the Anime Subtitle Pipeline project.

## Table of Contents

1. [Python Style Guide](#python-style-guide)
2. [Documentation Standards](#documentation-standards)
3. [Error Handling](#error-handling)
4. [Testing Guidelines](#testing-guidelines)
5. [Git Workflow](#git-workflow)
6. [Performance Considerations](#performance-considerations)

---

## Python Style Guide

### General Principles

- Follow [PEP 8](https://pep8.org/) style guide
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100 characters (120 for comments/docstrings)
- Use meaningful variable and function names

### Naming Conventions

```python
# Classes: PascalCase
class FasterWhisperASR:
    pass

# Functions and methods: snake_case
def extract_audio_with_ffmpeg():
    pass

# Constants: UPPER_SNAKE_CASE
MAX_DURATION_SEC = 7.0

# Private methods: _leading_underscore
def _apply_profile(self):
    pass

# Module-level "private" variables: _leading_underscore
_global_config = None
```

### Type Hints

Always use type hints for function signatures:

```python
from typing import List, Optional, Dict, Any
from pathlib import Path

def process_segments(
    segments: List[Segment],
    config: Config,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """Process segments and return results."""
    pass
```

### Imports

Organize imports in three groups, separated by blank lines:

```python
# Standard library
import json
import logging
from pathlib import Path
from typing import List, Optional

# Third-party packages
import torch
from transformers import MarianMTModel

# Local modules
from config import Config
from asr import Segment
```

---

## Documentation Standards

### Module Docstrings

Every module should have a comprehensive docstring:

```python
"""
Module name and brief description.

This module handles [detailed description of functionality].

Key features:
- Feature 1
- Feature 2
- Feature 3

Example:
    from module import function
    result = function(arg1, arg2)
"""
```

### Function Docstrings

Use Google-style docstrings:

```python
def extract_audio_with_ffmpeg(
    input_video_path: str,
    output_audio_path: str,
    audio_track_index: int = 0
) -> Path:
    """
    Extract audio track from video file using ffmpeg.
    
    Extracts audio to WAV format optimized for Whisper:
    - 16 kHz sample rate (Whisper's native rate)
    - Mono (1 channel)
    - PCM 16-bit signed integer format
    
    Args:
        input_video_path: Path to input video file
        output_audio_path: Path for output WAV file
        audio_track_index: Index of audio track to extract (default: 0)
        
    Returns:
        Path object pointing to the extracted audio file
        
    Raises:
        FileNotFoundError: If input video doesn't exist
        RuntimeError: If ffmpeg extraction fails
        
    Example:
        >>> audio_path = extract_audio_with_ffmpeg(
        ...     "video.mkv",
        ...     "temp/audio.wav",
        ...     audio_track_index=0
        ... )
        >>> print(audio_path)
        temp/audio.wav
    """
    pass
```

### Class Docstrings

```python
class FasterWhisperASR:
    """
    Japanese ASR using Faster-Whisper.
    
    This class wraps the Faster-Whisper library and provides a simple interface
    for transcribing Japanese audio to timestamped text segments.
    
    Attributes:
        config: Configuration object with ASR settings
        model: Loaded WhisperModel instance (None until load_model() called)
        
    Example:
        >>> config = Config()
        >>> asr = FasterWhisperASR(config)
        >>> segments = asr.transcribe_audio_to_segments("audio.wav")
        >>> asr.unload_model()
    """
    
    def __init__(self, config: Config):
        """
        Initialize the Faster-Whisper ASR model.
        
        Args:
            config: Configuration object with ASR settings
        """
        pass
```

### Inline Comments

Use inline comments sparingly, only for complex logic:

```python
# Good: Explains non-obvious logic
# Split timing proportionally across chunks
duration_per_chunk = seg.duration / len(text_chunks)

# Bad: States the obvious
# Increment counter
counter += 1
```

---

## Error Handling

### Exception Handling Best Practices

1. **Be specific** with exception types:

```python
# Good
try:
    with open(file_path, 'r') as f:
        data = json.load(f)
except FileNotFoundError:
    logger.error(f"File not found: {file_path}")
except json.JSONDecodeError as e:
    logger.error(f"Invalid JSON: {e}")

# Bad
try:
    with open(file_path, 'r') as f:
        data = json.load(f)
except Exception as e:
    logger.error(f"Error: {e}")
```

2. **Provide context** in error messages:

```python
# Good
raise RuntimeError(f"Failed to load model {model_name}: {error_details}")

# Bad
raise RuntimeError("Model loading failed")
```

3. **Use custom exceptions** for domain-specific errors:

```python
class SubtitleGenerationError(Exception):
    """Raised when subtitle generation fails."""
    pass

class ModelLoadError(Exception):
    """Raised when model loading fails."""
    pass
```

4. **Clean up resources** in finally blocks:

```python
temp_file = None
try:
    temp_file = Path("temp.wav")
    # Process file...
except Exception as e:
    logger.error(f"Processing failed: {e}")
    raise
finally:
    if temp_file and temp_file.exists():
        temp_file.unlink()
```

### Logging Best Practices

Use appropriate log levels:

```python
import logging

logger = logging.getLogger(__name__)

# DEBUG: Detailed diagnostic information
logger.debug(f"Processing segment {i}/{total}")

# INFO: General informational messages
logger.info("Model loaded successfully")

# WARNING: Something unexpected but recoverable
logger.warning("LLM endpoint not accessible, using raw translations")

# ERROR: Error that prevents specific operation
logger.error(f"Failed to process {file_name}: {error}")

# CRITICAL: Serious error that may cause program termination
logger.critical("CUDA out of memory, cannot continue")
```

---

## Testing Guidelines

### Unit Tests

Write unit tests for all public functions:

```python
import unittest
from pathlib import Path
from srt_writer import format_timestamp_srt

class TestSRTWriter(unittest.TestCase):
    """Test cases for SRT writer functions."""
    
    def test_format_timestamp_basic(self):
        """Test basic timestamp formatting."""
        result = format_timestamp_srt(90.5)
        self.assertEqual(result, "00:01:30,500")
    
    def test_format_timestamp_negative(self):
        """Test that negative timestamps raise ValueError."""
        with self.assertRaises(ValueError):
            format_timestamp_srt(-1.0)
    
    def test_format_timestamp_zero(self):
        """Test zero timestamp."""
        result = format_timestamp_srt(0.0)
        self.assertEqual(result, "00:00:00,000")
```

### Integration Tests

Test complete workflows:

```python
def test_complete_pipeline():
    """Test complete subtitle generation pipeline."""
    config = Config("test_config.yaml")
    
    # Extract audio
    audio_path = extract_audio_with_ffmpeg(
        "test_data/video.mkv",
        "temp/test_audio.wav"
    )
    
    # Transcribe
    asr = FasterWhisperASR(config)
    segments = asr.transcribe_audio_to_segments(str(audio_path))
    
    # Verify results
    assert len(segments) > 0
    assert all(seg.text_ja for seg in segments)
    
    # Cleanup
    audio_path.unlink()
```

### Test Data

- Keep test data small (< 1MB)
- Use synthetic or public domain content
- Store in `tests/data/` directory

---

## Git Workflow

### Commit Messages

Follow conventional commit format:

```
type(scope): brief description

Detailed explanation of changes (optional)

Fixes #123
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(asr): add support for Whisper large-v3-turbo

Implements support for the new Whisper large-v3-turbo model
with improved performance and accuracy.

fix(llm): handle connection timeout gracefully

Added retry logic and better error messages when LLM
endpoint is unavailable.

docs(api): add comprehensive API documentation

Created API_DOCUMENTATION.md with detailed examples
for all public classes and functions.
```

### Branch Naming

```
feature/add-whisper-turbo-support
bugfix/fix-llm-timeout
docs/update-readme
refactor/improve-error-handling
```

### Pull Request Guidelines

1. **Title**: Clear, descriptive summary
2. **Description**: Explain what and why
3. **Testing**: Describe how you tested changes
4. **Screenshots**: Include for UI changes
5. **Breaking Changes**: Clearly document any breaking changes

---

## Performance Considerations

### Memory Management

1. **Unload models** when not needed:

```python
# Good
asr = FasterWhisperASR(config)
segments = asr.transcribe_audio_to_segments(audio_path)
asr.unload_model()  # Free memory

# Bad
asr = FasterWhisperASR(config)
segments = asr.transcribe_audio_to_segments(audio_path)
# Model stays in memory
```

2. **Use generators** for large datasets:

```python
# Good: Memory efficient
def process_files(file_list):
    for file in file_list:
        yield process_single_file(file)

# Bad: Loads everything into memory
def process_files(file_list):
    return [process_single_file(f) for f in file_list]
```

3. **Batch operations** when possible:

```python
# Good: Batch translation
translations = translator.translate_batch(texts)

# Bad: One at a time
translations = [translator.translate_text(t) for t in texts]
```

### GPU Optimization

1. **Move tensors to GPU** only when needed
2. **Use appropriate batch sizes** for available VRAM
3. **Clear CUDA cache** after heavy operations:

```python
import torch

# After processing
torch.cuda.empty_cache()
```

### I/O Optimization

1. **Use Path objects** instead of strings:

```python
from pathlib import Path

# Good
path = Path("data/file.txt")
if path.exists():
    content = path.read_text()

# Less efficient
import os
if os.path.exists("data/file.txt"):
    with open("data/file.txt", 'r') as f:
        content = f.read()
```

2. **Buffer file operations**:

```python
# Good: Buffered write
with open(output_file, 'w', buffering=8192) as f:
    for line in lines:
        f.write(line)

# Bad: Unbuffered
with open(output_file, 'w', buffering=1) as f:
    for line in lines:
        f.write(line)
```

---

## Code Review Checklist

Before submitting code for review:

- [ ] Code follows PEP 8 style guide
- [ ] All functions have type hints
- [ ] All public functions have docstrings
- [ ] Error handling is appropriate
- [ ] Logging is used correctly
- [ ] Tests are included
- [ ] No hardcoded paths or credentials
- [ ] Memory is managed properly
- [ ] Performance is considered
- [ ] Documentation is updated

---

## Security Considerations

### Input Validation

Always validate user input:

```python
def process_video(video_path: str):
    """Process video file."""
    path = Path(video_path)
    
    # Validate file exists
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    
    # Validate file extension
    if path.suffix.lower() not in ['.mkv', '.mp4', '.avi']:
        raise ValueError(f"Unsupported format: {path.suffix}")
    
    # Validate file size (e.g., max 10GB)
    if path.stat().st_size > 10 * 1024 * 1024 * 1024:
        raise ValueError("File too large (max 10GB)")
```

### Sensitive Data

- **Never commit** API keys, passwords, or credentials
- Use environment variables for sensitive configuration
- Add sensitive files to `.gitignore`

```python
import os

# Good: Use environment variable
api_key = os.getenv("API_KEY")
if not api_key:
    raise ValueError("API_KEY environment variable not set")

# Bad: Hardcoded
api_key = "sk-1234567890abcdef"
```

### External Commands

Sanitize inputs when calling external commands:

```python
import subprocess
import shlex

# Good: Use list format (no shell injection)
cmd = ["ffmpeg", "-i", input_file, output_file]
subprocess.run(cmd, check=True)

# Bad: String format with shell=True
cmd = f"ffmpeg -i {input_file} {output_file}"
subprocess.run(cmd, shell=True)  # Vulnerable to injection
```

---

## Deprecation Policy

When deprecating features:

1. **Add deprecation warning** in code:

```python
import warnings

def old_function():
    """Deprecated function."""
    warnings.warn(
        "old_function is deprecated, use new_function instead",
        DeprecationWarning,
        stacklevel=2
    )
    return new_function()
```

2. **Update documentation** with migration guide
3. **Keep deprecated code** for at least one major version
4. **Remove in next major version**

---

## Questions?

If you have questions about contributing:

1. Check this guide
2. Review existing code for examples
3. Ask in project discussions
4. Open an issue for clarification

---

*Thank you for contributing to the Anime Subtitle Pipeline!*
