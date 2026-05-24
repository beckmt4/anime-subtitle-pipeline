# ============================================================================
# QUICK START GUIDE
# ============================================================================
# This guide walks you through setting up and running the anime subtitle
# pipeline for the first time.
# ============================================================================

## STEP 1: VERIFY PREREQUISITES
## ============================================================================

# Check Python version (3.9+ required)
python --version

# Check ffmpeg installation
ffmpeg -version

# Check CUDA availability (optional, for GPU)
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"


## STEP 2: INSTALL DEPENDENCIES
## ============================================================================

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install PyTorch (CPU-only; for GPU see README)
pip install torch

# Install other dependencies
pip install -r requirements.txt


## STEP 3: SET UP OLLAMA (OPTIONAL)
## ============================================================================

# Download Ollama from https://ollama.ai/ and install

# Pull the Qwen model
ollama pull qwen2.5:7b

# Start Ollama server (in a separate terminal)
ollama serve

# Verify it's running
curl http://localhost:11434/api/tags


## STEP 4: CONFIGURE THE PIPELINE
## ============================================================================

# Edit config.yaml:
# 1. Set profile: "dev" (for 6GB GPU) or "prod" (for 24GB GPU)
# 2. Set llm.enabled: true (if using Ollama) or false (to skip)
# 3. Set mux.enabled: false (just generate SRT) or true (mux into video)

# Example for dev box (6GB GPU):
runtime:
  profile: "dev"

llm:
  enabled: true  # Set to false if not using Ollama

mux:
  enabled: false  # Set to true to auto-mux SRT into video


## STEP 5: RUN YOUR FIRST SUBTITLE GENERATION
## ============================================================================

# Place a video file in the current directory
# For example: anime_episode.mkv

# Run the pipeline
python main.py anime_episode.mkv

# Output will be in:
# - outbox/anime_episode.en.srt     (subtitles)
# - outbox/anime_episode.en.qc.json (QC sidecar)


## STEP 6: ADVANCED OPTIONS
## ============================================================================

# Skip LLM polishing (faster, uses raw MT)
python main.py anime_episode.mkv --no-llm

# Use prod profile (if you have a 24GB GPU)
python main.py anime_episode.mkv --profile prod

# Generate SRT only (don't mux into video)
python main.py anime_episode.mkv --no-mux

# Use specific audio track
python main.py anime_episode.mkv --audio-track 1

# Enable debug logging
python main.py anime_episode.mkv --log-level DEBUG


## TROUBLESHOOTING
## ============================================================================

# CUDA Out of Memory?
# - Reduce batch size in config.yaml (asr.dev.batch_size: 4)
# - Use int8 quantization (asr.dev.compute_type: "int8")

# LLM Connection Failed?
# - Check if Ollama is running: curl http://localhost:11434/api/tags
# - Or skip LLM: python main.py video.mkv --no-llm

# No Japanese Audio Detected?
# - List tracks: ffprobe -v error -select_streams a -show_entries stream=index video.mkv
# - Specify track: python main.py video.mkv --audio-track 1

# ffmpeg Not Found?
# - Fedora/RHEL: sudo dnf install ffmpeg
# - Debian/Ubuntu: sudo apt-get install ffmpeg
# - macOS: brew install ffmpeg


## BATCH PROCESSING
## ============================================================================

# Process all MKV files in inbox/ directory
for file in inbox/*.mkv; do
    echo "Processing: $file"
    python main.py "$file"
done


## PERFORMANCE EXPECTATIONS
## ============================================================================

# Dev Box (RTX A3000 6GB):
# - Profile: dev
# - Speed: ~2-3x real-time
# - Example: 24 min episode → ~10 min processing

# Prod Box (RTX 4090 24GB):
# - Profile: prod  
# - Speed: ~5-10x real-time
# - Example: 24 min episode → ~3 min processing

# CPU-Only:
# - Speed: ~0.1-0.5x real-time
# - Example: 24 min episode → ~60+ min processing
# - Consider using smaller Whisper model


## FIRST RUN NOTES
## ============================================================================

# First run will download models:
# - Whisper Large V3 Turbo (~1.5 GB)
# - Helsinki-NLP opus-mt-ja-en (~300 MB)
# 
# These are cached in:
# - Windows: C:\Users\YourName\.cache\huggingface\hub\
# - Linux/macOS: ~/.cache/huggingface/hub/
#
# Ollama models (if used) are stored in:
# - Windows: C:\Users\YourName\.ollama\models\
# - Linux/macOS: ~/.ollama/models/


## EXAMPLE OUTPUT
## ============================================================================

# Console output will show:
# ======================================================================
# Processing: anime_episode.mkv
# ======================================================================
# 
# [1/6] Extracting audio track from video...
# Audio extracted successfully: anime_episode.wav (42.3 MB)
# 
# [2/6] Running Japanese ASR (Faster-Whisper)...
# Model loaded successfully
# Transcription complete: 487 segments
# 
# [3/6] Translating Japanese to English (MarianMT)...
# Translation complete
# 
# [4/6] Polishing subtitles with LLM...
# Polishing complete
# 
# [5/6] Writing SRT subtitle file...
# ✓ SRT file created: outbox/anime_episode.en.srt
# 
# [6/6] Skipping video muxing (disabled)
# 
# ======================================================================
# ✓ Processing complete!
#   SRT file: outbox/anime_episode.en.srt
# ======================================================================


## NEXT STEPS
## ============================================================================

# 1. Test the generated SRT file:
#    - Open video with VLC and load the SRT
#    - Check timing and translation quality
#
# 2. Adjust config.yaml if needed:
#    - Change LLM style to "literal" for more literal translations
#    - Adjust max_chars_per_line for different subtitle widths
#    - Enable muxing to embed subtitles in video
#
# 3. Process more videos:
#    - Place videos in inbox/ directory
#    - Run batch processing script
#
# 4. Optimize for your hardware:
#    - If OOM errors: reduce batch sizes
#    - If too slow on CPU: consider cloud GPU or smaller models
#    - If subtitles too literal: ensure LLM is enabled and working

# ============================================================================
# You're all set! Happy subtitle generating! 🎬
# ============================================================================
