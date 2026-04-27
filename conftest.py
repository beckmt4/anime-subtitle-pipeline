"""pytest configuration — project root.

Stubs out heavy ML/GPU packages so all source modules can be imported
in CI without installing faster-whisper, transformers, torch, or
opentelemetry. Applies to tests in both the repo root and tests/.

Only stubs a package when it cannot be found on the system — so dev
machines with the real packages installed use those instead.
"""
import importlib.util
import sys
from unittest.mock import MagicMock

_HEAVY_STUBS = [
    # ASR backend
    "faster_whisper",
    "faster_whisper.audio",
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
    base_mod = _mod.split(".")[0]
    try:
        spec = importlib.util.find_spec(base_mod)
    except ValueError:
        # find_spec raises ValueError when a module has been injected into
        # sys.modules without a valid __spec__ (e.g. by a pytest plugin).
        # Treat this the same as "not found" so MagicMock stubs are used.
        spec = None
    if spec is None:
        sys.modules.setdefault(_mod, MagicMock())
