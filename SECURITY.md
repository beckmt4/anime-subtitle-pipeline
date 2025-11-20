# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Security Best Practices

### 1. Local-Only Operation

This pipeline is designed to run **100% locally** with no external API calls except to your local Ollama instance.

**Security Benefits:**
- No data leaves your machine
- No cloud service dependencies
- No API keys or credentials required
- Full control over your data

**Verify Local Operation:**
```bash
# Check that LLM endpoint is localhost
grep "base_url" config.yaml
# Should show: base_url: "http://localhost:11434"
```

### 2. Input Validation

#### File Path Validation

Always validate file paths to prevent directory traversal attacks:

```python
from pathlib import Path

def safe_path_check(user_path: str, base_dir: str) -> Path:
    """
    Safely resolve and validate a user-provided path.
    
    Args:
        user_path: User-provided path
        base_dir: Base directory to restrict access to
        
    Returns:
        Validated Path object
        
    Raises:
        ValueError: If path is outside base directory
    """
    base = Path(base_dir).resolve()
    target = (base / user_path).resolve()
    
    # Ensure target is within base directory
    if not str(target).startswith(str(base)):
        raise ValueError(f"Path outside base directory: {user_path}")
    
    return target
```

#### File Type Validation

Validate file extensions and MIME types:

```python
ALLOWED_VIDEO_EXTENSIONS = {'.mkv', '.mp4', '.avi', '.mov', '.m4v', '.webm'}

def validate_video_file(file_path: str) -> bool:
    """Validate that file is an allowed video format."""
    path = Path(file_path)
    
    # Check extension
    if path.suffix.lower() not in ALLOWED_VIDEO_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    
    # Check file exists and is a file (not directory)
    if not path.is_file():
        raise ValueError(f"Not a valid file: {file_path}")
    
    return True
```

#### File Size Limits

Prevent resource exhaustion with file size limits:

```python
MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10 GB

def check_file_size(file_path: str) -> bool:
    """Check if file size is within limits."""
    size = Path(file_path).stat().st_size
    
    if size > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {size / (1024**3):.1f} GB (max: 10 GB)")
    
    return True
```

### 3. External Command Execution

#### Safe ffmpeg Usage

Always use list format for subprocess commands:

```python
import subprocess

# SAFE: List format prevents shell injection
cmd = [
    "ffmpeg",
    "-i", input_file,
    "-ar", "16000",
    "-ac", "1",
    output_file
]
subprocess.run(cmd, check=True, capture_output=True)

# UNSAFE: String format with shell=True
# cmd = f"ffmpeg -i {input_file} -ar 16000 -ac 1 {output_file}"
# subprocess.run(cmd, shell=True)  # NEVER DO THIS
```

#### Command Timeout

Always set timeouts to prevent hanging:

```python
try:
    result = subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        timeout=300  # 5 minute timeout
    )
except subprocess.TimeoutExpired:
    logger.error("Command timed out")
    raise
```

### 4. Model Security

#### Model Source Verification

Models are downloaded from trusted sources:

- **Whisper**: OpenAI via Hugging Face
- **MarianMT**: Helsinki-NLP via Hugging Face
- **Qwen**: Alibaba via Ollama

**Verify model checksums** (optional but recommended):

```python
import hashlib

def verify_file_hash(file_path: str, expected_hash: str) -> bool:
    """Verify file SHA256 hash."""
    sha256 = hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    
    actual_hash = sha256.hexdigest()
    return actual_hash == expected_hash
```

#### Model Isolation

Models run in isolated processes:

- ASR: Separate process via faster-whisper
- MT: Separate process via transformers
- LLM: Separate process via Ollama

### 5. Dependency Security

#### PyTorch Security

**CRITICAL**: Use PyTorch 2.6+ to avoid CVE-2025-32434:

```bash
# Check PyTorch version
python -c "import torch; print(torch.__version__)"

# Upgrade if needed
pip install --upgrade torch>=2.6.0
```

#### Regular Updates

Keep dependencies updated:

```bash
# Check for outdated packages
pip list --outdated

# Update specific package
pip install --upgrade package-name

# Update all packages (use with caution)
pip install --upgrade -r requirements.txt
```

#### Vulnerability Scanning

Use safety to check for known vulnerabilities:

```bash
# Install safety
pip install safety

# Scan dependencies
safety check

# Scan requirements file
safety check -r requirements.txt
```

### 6. Configuration Security

#### Sensitive Configuration

Never commit sensitive data:

```yaml
# config.yaml - GOOD
llm:
  base_url: "http://localhost:11434"  # Local only

# config.yaml - BAD (never do this)
# api:
#   key: "sk-1234567890abcdef"  # NEVER commit API keys
```

#### Environment Variables

Use environment variables for sensitive config:

```python
import os

# Load from environment
llm_endpoint = os.getenv("LLM_ENDPOINT", "http://localhost:11434")
api_key = os.getenv("API_KEY")  # If ever needed

# Validate
if not llm_endpoint.startswith(("http://localhost", "http://127.0.0.1")):
    logger.warning(f"Non-localhost endpoint: {llm_endpoint}")
```

#### File Permissions

Set appropriate file permissions:

```bash
# Config files: readable by owner only
chmod 600 config.yaml

# Scripts: executable by owner only
chmod 700 main.py

# Output directory: owner read/write
chmod 700 outbox/
```

### 7. Network Security

#### LLM Endpoint Validation

Validate LLM endpoint is localhost:

```python
from urllib.parse import urlparse

def validate_llm_endpoint(url: str) -> bool:
    """Ensure LLM endpoint is localhost only."""
    parsed = urlparse(url)
    
    # Only allow localhost
    if parsed.hostname not in ['localhost', '127.0.0.1', '::1']:
        raise ValueError(f"LLM endpoint must be localhost, got: {parsed.hostname}")
    
    # Only allow HTTP (not HTTPS for local)
    if parsed.scheme != 'http':
        logger.warning(f"Unexpected scheme: {parsed.scheme}")
    
    return True
```

#### Firewall Configuration

Ensure Ollama only listens on localhost:

```bash
# Check Ollama is bound to localhost
netstat -an | grep 11434

# Should show: 127.0.0.1:11434 (not 0.0.0.0:11434)
```

### 8. Temporary File Security

#### Secure Temp Files

Use secure temporary file creation:

```python
import tempfile
from pathlib import Path

# Create secure temp file
with tempfile.NamedTemporaryFile(
    mode='w',
    suffix='.wav',
    delete=False,
    dir='temp/'
) as tmp:
    temp_path = Path(tmp.name)
    # Use temp file...

# Clean up
try:
    # Process file...
    pass
finally:
    if temp_path.exists():
        temp_path.unlink()
```

#### Temp Directory Cleanup

Regularly clean temporary files:

```python
import time
from pathlib import Path

def cleanup_old_temp_files(temp_dir: str, max_age_hours: int = 24):
    """Remove temporary files older than max_age_hours."""
    temp_path = Path(temp_dir)
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    for file in temp_path.glob('*'):
        if file.is_file():
            age = current_time - file.stat().st_mtime
            if age > max_age_seconds:
                try:
                    file.unlink()
                    logger.info(f"Cleaned up old temp file: {file.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete {file.name}: {e}")
```

### 9. Logging Security

#### Sanitize Log Output

Never log sensitive information:

```python
import logging

logger = logging.getLogger(__name__)

# GOOD: Log without sensitive data
logger.info(f"Processing file: {Path(file_path).name}")

# BAD: Might log full paths with usernames
# logger.info(f"Processing file: {file_path}")

# GOOD: Sanitize before logging
def sanitize_path(path: str) -> str:
    """Return only filename, not full path."""
    return Path(path).name

logger.info(f"Processing: {sanitize_path(file_path)}")
```

#### Log File Permissions

Protect log files:

```bash
# Set restrictive permissions on logs
chmod 600 logs/*.json
chmod 600 logs/*.log
```

### 10. Error Handling Security

#### Don't Leak Information

Avoid exposing system details in error messages:

```python
# GOOD: Generic error message
try:
    process_file(file_path)
except Exception as e:
    logger.error(f"Processing failed: {type(e).__name__}")
    raise RuntimeError("File processing failed")

# BAD: Exposes system details
# except Exception as e:
#     raise RuntimeError(f"Failed: {e} at {file_path} on {os.uname()}")
```

#### Safe Error Responses

Return safe error messages to users:

```python
def safe_error_message(error: Exception) -> str:
    """Convert exception to safe user-facing message."""
    error_map = {
        FileNotFoundError: "File not found",
        PermissionError: "Permission denied",
        ValueError: "Invalid input",
        RuntimeError: "Processing error"
    }
    
    return error_map.get(type(error), "An error occurred")
```

## Reporting a Vulnerability

If you discover a security vulnerability:

1. **DO NOT** open a public issue
2. Email security details to: [your-email@example.com]
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 48 hours and work with you to address the issue.

## Security Checklist

Before deploying:

- [ ] All dependencies are up to date
- [ ] PyTorch version is 2.6 or higher
- [ ] LLM endpoint is localhost only
- [ ] No API keys or credentials in code
- [ ] File paths are validated
- [ ] Subprocess calls use list format
- [ ] Timeouts are set for external commands
- [ ] Temporary files are cleaned up
- [ ] Log files don't contain sensitive data
- [ ] File permissions are restrictive
- [ ] Input validation is comprehensive

## Security Updates

### Version 1.0.0 (Current)

- ✅ Local-only operation
- ✅ No external API dependencies
- ✅ PyTorch 2.6+ requirement
- ✅ Input validation
- ✅ Safe subprocess execution
- ✅ Secure temporary file handling

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [PyTorch Security](https://pytorch.org/docs/stable/notes/security.html)
- [Hugging Face Model Security](https://huggingface.co/docs/hub/security)

---

*Last Updated: 2025*
