# Changelog

All notable changes to the Anime Subtitle Pipeline will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-XX

### Added

#### Core Features
- Complete subtitle generation pipeline (Video → Audio → ASR → MT → LLM → SRT)
- Whisper Large V3 Turbo support for Japanese ASR
- Helsinki-NLP MarianMT for Japanese-to-English translation
- Qwen 2.5 LLM integration for subtitle polishing via Ollama
- Automatic Japanese audio track detection
- SRT subtitle file generation with proper formatting
- Optional video muxing to embed subtitles
- JSON logging for detailed segment data

#### Configuration
- YAML-based configuration system
- Dev/Prod profile support for different hardware
- Configurable quantization (int8_float16 for dev, float16 for prod)
- Adjustable batch sizes per profile
- LLM style selection (natural vs literal)
- Subtitle formatting constraints (line count, character limits)

#### Performance
- GPU acceleration with automatic CUDA detection
- Configurable compute types for memory optimization
- Batch processing for efficient translation
- Voice Activity Detection (VAD) for silence filtering
- Lazy model loading for memory efficiency

#### CLI Tools
- `main.py` - Main subtitle generation pipeline
- `batch_process.py` - Batch processing multiple videos
- `benchmark_configs.py` - Configuration benchmarking
- `build_dataset.py` - Training dataset creation
- `compare_subtitles.py` - Subtitle comparison tool
- `extract_training_data.py` - Training data extraction
- `evaluate_subtitles.py` - Subtitle quality evaluation

#### Observability
- OpenTelemetry tracing support
- Console and OTLP exporters
- Span instrumentation for all pipeline stages
- Detailed logging with configurable levels
- JSON segment logs for analysis

#### Documentation
- Comprehensive README with installation and usage
- API documentation with examples
- Contributing guide with code standards
- Security policy and best practices
- Quick start guide
- Project summary
- File overview

### Security

#### Implemented
- Local-only operation (no cloud dependencies)
- PyTorch 2.6+ requirement (CVE-2025-32434 mitigation)
- Input validation for file paths and types
- Safe subprocess execution (no shell injection)
- Localhost-only LLM endpoint validation
- Secure temporary file handling
- Sanitized logging (no sensitive data)

#### Best Practices
- Type hints for all public functions
- Comprehensive error handling
- Resource cleanup (model unloading, temp file deletion)
- Timeout protection for external commands
- File size limits to prevent resource exhaustion

### Dependencies

#### Core
- Python 3.9+
- PyTorch 2.6+
- faster-whisper 1.0+
- transformers 4.35+
- pyyaml 6.0+
- requests 2.31+

#### Optional
- tqdm (progress bars)
- OpenTelemetry (tracing)
- sacrebleu (evaluation metrics)

#### External
- ffmpeg (audio extraction and video muxing)
- Ollama (optional, for LLM polishing)

### Hardware Support

#### Minimum (Dev Profile)
- GPU: NVIDIA RTX A3000 6GB or equivalent
- RAM: 16 GB
- Storage: 20 GB
- Performance: ~2-3x realtime

#### Recommended (Prod Profile)
- GPU: NVIDIA RTX 4090 24GB or equivalent
- RAM: 32 GB
- Storage: 30 GB
- Performance: ~5-10x realtime

#### CPU-Only
- Supported but significantly slower (0.1-0.5x realtime)
- Recommended for testing only

### Known Issues

#### Limitations
- SRT format only (no ASS/SSA support yet)
- Japanese audio only (no multi-language support)
- Requires ffmpeg in PATH
- LLM polishing requires Ollama server

#### Workarounds
- ASR model unloading disabled due to destructor crash (temporary)
- Manual audio track selection available if auto-detection fails
- LLM can be disabled with `--no-llm` flag

### Performance Benchmarks

#### Dev Profile (RTX A3000 6GB)
- Model: Whisper large-v3-turbo (int8_float16)
- Batch size: 8
- Speed: ~2-3x realtime
- VRAM usage: ~4-5 GB

#### Prod Profile (RTX 4090 24GB)
- Model: Whisper large-v3-turbo (float16)
- Batch size: 16
- Speed: ~5-10x realtime
- VRAM usage: ~8-10 GB

### Breaking Changes

None (initial release)

### Deprecated

None (initial release)

### Removed

None (initial release)

### Fixed

None (initial release)

---

## [Unreleased]

### Added

- Added automatic SQLite artifact-registry migrations with a persistent
  `schema_migrations` table, ordered `docs/migrations/*.sql` execution, and
  checksum protection for already-applied migration files.
- Added `docs/migrations/README.md` to document migration naming and immutability
  expectations.
- Wired the legacy `process_video()` path into `ArtifactRegistry` so it records
  media assets, pipeline run status, ASR/MT/LLM candidate lineage, SRT artifacts,
  and linked muxed MKV artifacts when registry storage is available.
- Added registry read helpers for media run history, latest artifact lookup, and
  candidate lineage traversal.
- Added explicit `ProcessingLedger` run-history helpers for UI/automation:
  `list_pipeline_runs()` and `get_latest_run_for_media()`.
- Added script-friendly CLI output for recorded registry runs:
  `registry_run_id=<id>`.
- Documented and tested `LLM_BASE_URL` so deployments can override the Ollama
  endpoint without editing `config.yaml`.
- Added validation and tests for `subtitle_corrector.py --timeout`.
- Improved `subtitle_corrector.py` drift detection so all-caps proper nouns are
  protected while case-only output changes are allowed.

### Planned Features

#### Short Term (v1.1.0)
- [ ] ASS/SSA subtitle format support
- [ ] Multi-language audio support (Korean, Chinese)
- [ ] Improved LLM prompt templates
- [ ] Batch processing progress bars
- [ ] Configuration validation tool
- [ ] Model caching improvements

#### Medium Term (v1.2.0)
- [ ] Web UI for easier usage
- [ ] Real-time subtitle preview
- [ ] Subtitle editor integration
- [ ] Custom model fine-tuning support
- [ ] Advanced timing adjustment
- [ ] Subtitle style customization

#### Long Term (v2.0.0)
- [ ] Multi-speaker detection
- [ ] Character name detection
- [ ] Emotion/tone analysis
- [ ] Context-aware translation
- [ ] Translation memory system
- [ ] Cloud deployment option

### Potential Improvements

#### Performance
- [ ] Model quantization optimization
- [ ] Parallel processing for multiple files
- [ ] Streaming transcription support
- [ ] GPU memory optimization
- [ ] Faster LLM inference

#### Quality
- [ ] Better punctuation handling
- [ ] Improved line breaking algorithm
- [ ] Context window for LLM
- [ ] Translation consistency checks
- [ ] Quality metrics dashboard

#### Usability
- [ ] Interactive configuration wizard
- [ ] Automatic hardware detection
- [ ] One-click installer
- [ ] Docker container support
- [ ] GUI application

---

## Version History

### Version Numbering

We use [Semantic Versioning](https://semver.org/):

- **MAJOR** version: Incompatible API changes
- **MINOR** version: New functionality (backwards compatible)
- **PATCH** version: Bug fixes (backwards compatible)

### Release Schedule

- **Patch releases**: As needed for critical bugs
- **Minor releases**: Every 2-3 months
- **Major releases**: Annually or for breaking changes

### Support Policy

- **Current version (1.0.x)**: Full support
- **Previous minor (N-1)**: Security fixes only
- **Older versions**: No support

---

## Migration Guides

### Upgrading to 1.0.0

Initial release - no migration needed.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- How to report bugs
- How to suggest features
- How to submit pull requests
- Code style guidelines
- Testing requirements

---

## Security

See [SECURITY.md](SECURITY.md) for:
- Security best practices
- Vulnerability reporting
- Security updates

---

*For detailed API changes, see [API_DOCUMENTATION.md](API_DOCUMENTATION.md)*
