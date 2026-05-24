# API Documentation (Current `core/` Architecture)

This document reflects the current public API surface used by the supported
pipeline workflows. Root-shim imports such as `from config import ...` are
deprecated; new code should import from `core.*`.

## Runtime and orchestration

```python
from core.runtime import Config, set_config, run_generate
from core.media import inspect_media

cfg = Config("config.yaml")
set_config(cfg)

media = inspect_media("video.mkv")
result = run_generate(media, cfg, no_llm=False, inspect_only=False)
print(result["strategy"], result["output_srt"])
```

## Media inspection

```python
from core.media import inspect_media, choose_audio_track

media = inspect_media("video.mkv")
best_audio_order = choose_audio_track(media, preferred_languages=["ja", "en"])
```

Key types:
- `core.media.MediaInfo`
- `core.media.AudioStream`
- `core.media.SubtitleStream`

## Extraction

```python
from core.extract.audio_utils import extract_audio_with_ffmpeg, mux_subtitle_to_video
from core.extract.subtitle_utils import extract_subtitle_track, discover_sidecar_subtitles
```

## ASR, translation, and polish

```python
from core.asr import FasterWhisperASR, transcribe_audio_to_candidate
from core.mt import translate_candidate_jp_to_en, translate_candidate_jp_to_en_workflow
from core.polish import polish_candidate_with_llm, enforce_constraints_on_candidate
```

## Subtitle models and writing

```python
from core.subtitles import Segment, SubtitleCandidate, write_candidate_srt
```

## Benchmarking

```python
from core.benchmark import run_benchmark
```

## Review workflow

```python
from core.review import (
    list_review_queue,
    render_local_review_ui,
    approve_review_task,
    reject_review_task,
)
```

## Artifacts and processing ledger

```python
from core.artifacts import ArtifactRegistry, ProcessingLedger
from core.artifacts.pipeline_wiring import compute_media_hash, open_registry
```

## Notes

- Supported CLI entrypoint: `main.py`
- Supported modes: `generate`, `benchmark`, `review`, `subtitle` (deprecated
  alias of `generate`)
- Import examples are cross-checked against `docs/QUICK_REFERENCE.md` for any
  shared symbols.
- Lightweight validation path for docs import examples:
  - `python -m pytest -v tests/test_architecture_guard.py -k "QuickReferenceFreshness or ApiDocumentationFreshness"`
- For module ownership and boundaries, see:
  - `docs/FILE_OVERVIEW.md`
  - `docs/architecture/module-boundaries.md`
