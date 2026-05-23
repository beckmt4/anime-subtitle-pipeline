"""Export review-approved translation-memory records into JSONL datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.translation import TranslationMemoryStore, export_translation_memory_datasets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export approved review corrections to benchmark/training JSONL datasets."
    )
    parser.add_argument("--memory-path", required=True, help="Path to translation-memory JSONL.")
    parser.add_argument(
        "--approved-output",
        default="artifacts/review_exports/approved_corrections.jsonl",
        help="Output path for normalized approved correction JSONL.",
    )
    parser.add_argument(
        "--benchmark-output",
        default="fixtures/translation_eval/approved_references.jsonl",
        help="Optional benchmark fixture output path.",
    )
    parser.add_argument(
        "--sft-output",
        default="artifacts/training/ja_en_subtitle_sft.jsonl",
        help="Optional SFT dataset output path.",
    )
    parser.add_argument(
        "--preference-output",
        default="artifacts/training/ja_en_preference_pairs.jsonl",
        help="Optional preference-pair dataset output path.",
    )
    parser.add_argument("--source-lang", default=None, help="Filter by source language (e.g. ja).")
    parser.add_argument("--target-lang", default=None, help="Filter by target language (e.g. en).")
    parser.add_argument("--domain", default=None, help="Filter by domain (e.g. anime).")
    parser.add_argument("--skip-benchmark", action="store_true", help="Skip benchmark fixture export.")
    parser.add_argument("--skip-sft", action="store_true", help="Skip SFT dataset export.")
    parser.add_argument(
        "--skip-preference",
        action="store_true",
        help="Skip preference-pair dataset export.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    memory = TranslationMemoryStore(Path(args.memory_path))
    summary = export_translation_memory_datasets(
        memory,
        approved_output_path=Path(args.approved_output),
        benchmark_output_path=None if args.skip_benchmark else Path(args.benchmark_output),
        sft_output_path=None if args.skip_sft else Path(args.sft_output),
        preference_output_path=None if args.skip_preference else Path(args.preference_output),
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        domain=args.domain,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
