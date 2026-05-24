"""core.benchmark.config — BenchmarkConfig dataclass.

Centralises all benchmark-related config reads so that ``run_benchmark``
and tests can access a typed, validated configuration object rather than
calling ``config.get(...)`` scattered throughout the code.

Usage::

    from core.benchmark.config import BenchmarkConfig
    bc = BenchmarkConfig.from_config(config)
    print(bc.reference_priority)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from core.runtime.config import Config

logger = logging.getLogger(__name__)

# Known translation engine names.  New engines added to the pipeline should
# be listed here.  Unknown names are warned about but not rejected so that
# custom or future engines work without code changes.
KNOWN_TRANSLATION_ENGINES = frozenset({"marian", "llm_direct", "hybrid"})


# Default reference-selection priority used when the config key is absent.
DEFAULT_REFERENCE_PRIORITY: List[str] = [
    "embedded_en",
    "en_audio_asr",
    "ja_audio_asr_mt",
    "embedded_jp_mt",
]

# Default translation engines when none are configured.
DEFAULT_TRANSLATION_ENGINES: List[str] = ["marian"]


@dataclass
class BenchmarkConfig:
    """Typed snapshot of all benchmark-related configuration.

    Attributes:
        use_embedded_en:          Include embedded English subtitle tracks.
        use_embedded_jp:          Include embedded Japanese subtitle tracks (→ MT).
        use_en_audio:             Include English audio tracks (→ ASR).
        use_ja_audio:             Include Japanese audio tracks (→ ASR → MT).
        compare_all_pairs:        Compute full N×N pairwise comparison matrix in
                                  addition to the reference-only comparisons.
        max_diffs_per_comparison: Maximum number of diff entries stored per
                                  comparison in the output JSON.
        reference_priority:       Ordered list of candidate-ID substrings used
                                  to select the reference candidate.
        translation_engines:      List of translation engine names to use for
                                  Japanese → English MT candidates.
    """

    use_embedded_en: bool = True
    use_embedded_jp: bool = True
    use_en_audio: bool = True
    use_ja_audio: bool = True
    compare_all_pairs: bool = False
    max_diffs_per_comparison: int = 20
    reference_priority: List[str] = field(default_factory=lambda: list(DEFAULT_REFERENCE_PRIORITY))
    translation_engines: List[str] = field(default_factory=lambda: list(DEFAULT_TRANSLATION_ENGINES))

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: "Config") -> "BenchmarkConfig":
        """Build a :class:`BenchmarkConfig` from a loaded :class:`~config.Config`.

        Resolution order for ``translation_engines``:
        1. ``benchmark.translation_engines``
        2. ``translation.benchmark_engines``
        3. ``[translation.engine]`` (single engine, fallback)
        4. ``["marian"]`` (hard default)

        Args:
            config: A loaded :class:`~config.Config` instance.

        Returns:
            Populated :class:`BenchmarkConfig`.
        """
        sources = config.get("benchmark", "sources", default={}) or {}

        # Translation engines — multi-source resolution
        engines = config.get("benchmark", "translation_engines", default=None)
        if engines is None:
            engines = config.get("translation", "benchmark_engines", default=None)
        if engines is None:
            single = config.get("translation", "engine", default="marian")
            engines = [single]
        if isinstance(engines, str):
            engines = [engines]
        engines = [str(e).strip().lower() for e in engines]

        # Warn about unrecognised engine names so misconfigurations surface early.
        for eng in engines:
            if eng not in KNOWN_TRANSLATION_ENGINES:
                logger.warning(
                    "Unknown translation engine %r in benchmark config; "
                    "known engines: %s",
                    eng,
                    ", ".join(sorted(KNOWN_TRANSLATION_ENGINES)),
                )

        return cls(
            use_embedded_en=bool(sources.get("use_embedded_en", True)),
            use_embedded_jp=bool(sources.get("use_embedded_jp", True)),
            use_en_audio=bool(sources.get("use_en_audio", True)),
            use_ja_audio=bool(sources.get("use_ja_audio", True)),
            compare_all_pairs=bool(
                config.get("benchmark", "compare_all_pairs", default=False)
            ),
            max_diffs_per_comparison=int(
                config.get("benchmark", "max_diffs_per_comparison", default=20)
            ),
            reference_priority=list(
                config.get(
                    "benchmark", "reference_priority",
                    default=DEFAULT_REFERENCE_PRIORITY,
                )
            ),
            translation_engines=engines,
        )


__all__ = [
    "BenchmarkConfig",
    "DEFAULT_REFERENCE_PRIORITY",
    "DEFAULT_TRANSLATION_ENGINES",
    "KNOWN_TRANSLATION_ENGINES",
]
