"""pytest configuration for tests/.

Stubs out heavy ML/GPU packages so all source modules can be imported
in CI without installing faster-whisper, transformers, torch, or
opentelemetry. When those packages are actually installed (dev machine),
setdefault is a no-op so the real packages are used instead.
"""
import sys
from unittest.mock import MagicMock

_HEAVY_STUBS = [
    # ASR backend
    "faster_whisper",
    # GPU / ML
    "torch",
    "transformers",
    "sentencepiece",
    "sacremoses",
    "ctranslate2",
    # Subtitle parsing
    "pysubs2",
    # Progress bars
    "tqdm",
    # OpenTelemetry stack — tracing.py imports these at module level
    "opentelemetry",
    "opentelemetry.api",
    "opentelemetry.trace",
    "opentelemetry.sdk",
    "opentelemetry.sdk.resources",
    "opentelemetry.sdk.trace",
    "opentelemetry.sdk.trace.export",
    "opentelemetry.exporter",
    "opentelemetry.exporter.otlp",
    "opentelemetry.exporter.otlp.proto",
    "opentelemetry.exporter.otlp.proto.http",
    "opentelemetry.exporter.otlp.proto.http.trace_exporter",
    "opentelemetry.instrumentation",
    "opentelemetry.instrumentation.requests",
    "opentelemetry.instrumentation.logging",
]

for _mod in _HEAVY_STUBS:
    sys.modules.setdefault(_mod, MagicMock())
