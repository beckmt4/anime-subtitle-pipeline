"""Subtitle pipeline entrypoint — batch-processes SRT files through subtitle_corrector.

For each input SRT file this script:
  1. Checks whether a corrected output already exists and is newer (skip).
  2. Runs subtitle_corrector.correct_srt_ex() to get grammar-corrected text.
  3. Compares the raw input bytes to the corrected output bytes (SHA-256).
  4. Writes the output only when content actually changed.
  5. Appends one JSON line per file to the pipeline log.

Exit codes:
  0 — all files ok or skipped
  1 — one or more files failed (exception)
  2 — one or more files had no_change (Ollama ran but output is identical to input)

Usage:
  python subtitle_pipeline.py episode.srt
  python subtitle_pipeline.py inbox/*.srt --output-dir /mnt/user/videos/outbox
  python subtitle_pipeline.py episode.srt --model llama3 --log /tmp/pipe.log
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from subtitle_corrector import correct_srt_ex, parse_srt

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = os.environ.get("PIPELINE_LOG", "./subtitle_pipeline.log")

# When a model produces no_change, suggest this fallback in the log entry.
_FALLBACK_MODEL: dict = {
    "mistral": "llama3",
    "llama3": "qwen2.5:7b",
    "qwen2.5:7b": "llama3.1",
}
_DEFAULT_FALLBACK = "llama3"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fallback_model(model: str) -> str:
    return _FALLBACK_MODEL.get(model, _DEFAULT_FALLBACK)


def _append_log(log_path: str, entry: dict) -> None:
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError as exc:
        logger.warning("Could not write pipeline log %s: %s", log_path, exc)


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_file(
    input_path: Path,
    output_path: Path,
    model: str,
    log_path: str,
    batch_size: int = 20,
    timeout: int = 120,
    verbose: bool = False,
    drift_log: Optional[str] = None,
) -> str:
    """Process one SRT file. Returns status: 'ok' | 'skipped' | 'no_change' | 'failed'."""
    filename = input_path.name

    # --- skip check ---
    if output_path.exists() and output_path.stat().st_mtime > input_path.stat().st_mtime:
        logger.info("[pipeline] SKIPPED %s (output is newer)", filename)
        entry = {
            "timestamp": _now_iso(),
            "file": filename,
            "status": "skipped",
            "cues_in": None,
            "cues_out": None,
            "drift_count": None,
            "error": None,
        }
        _append_log(log_path, entry)
        return "skipped"

    try:
        raw_content = input_path.read_text(encoding="utf-8")
        cues = parse_srt(raw_content)
        if not cues:
            raise ValueError(f"No cues parsed from {filename}")

        corrected_srt, stats = correct_srt_ex(
            cues,
            model=model,
            batch_size=batch_size,
            timeout=timeout,
            verbose=verbose,
            drift_log=drift_log,
            label=filename,
        )

        input_hash = _sha256(raw_content)
        output_hash = _sha256(corrected_srt)

        if input_hash == output_hash:
            logger.warning("[pipeline] NO_CHANGE %s — output identical to input", filename)
            entry = {
                "timestamp": _now_iso(),
                "file": filename,
                "status": "no_change",
                "cues_in": stats.cues_in,
                "cues_out": stats.cues_out,
                "drift_count": stats.drift_reverted,
                "error": None,
                "retry_with_model": _fallback_model(model),
            }
            _append_log(log_path, entry)
            return "no_change"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(corrected_srt, encoding="utf-8")
        logger.info("[pipeline] OK %s → %s", filename, output_path.name)

        entry = {
            "timestamp": _now_iso(),
            "file": filename,
            "status": "ok",
            "cues_in": stats.cues_in,
            "cues_out": stats.cues_out,
            "drift_count": stats.drift_reverted,
            "error": None,
        }
        _append_log(log_path, entry)
        return "ok"

    except Exception as exc:
        logger.error("[pipeline] FAILED %s: %s", filename, exc, exc_info=True)
        entry = {
            "timestamp": _now_iso(),
            "file": filename,
            "status": "failed",
            "cues_in": None,
            "cues_out": None,
            "drift_count": None,
            "error": str(exc),
        }
        _append_log(log_path, entry)
        return "failed"


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_pipeline(
    input_files: List[Path],
    output_dir: Optional[Path],
    model: str,
    log_path: str,
    batch_size: int = 20,
    timeout: int = 120,
    verbose: bool = False,
    drift_log: Optional[str] = None,
) -> int:
    """Process all input files. Returns exit code (0, 1, or 2)."""
    counts = {"ok": 0, "skipped": 0, "no_change": 0, "failed": 0}

    for input_path in input_files:
        if output_dir is not None:
            out = output_dir / input_path.name
        else:
            out = input_path.with_suffix(".corrected.srt")

        status = process_file(
            input_path=input_path,
            output_path=out,
            model=model,
            log_path=log_path,
            batch_size=batch_size,
            timeout=timeout,
            verbose=verbose,
            drift_log=drift_log,
        )
        counts[status] = counts.get(status, 0) + 1

    log_name = Path(log_path).name
    print(
        f"Pipeline complete: {counts['ok']} ok, {counts['skipped']} skipped, "
        f"{counts['failed']} failed, {counts['no_change']} no_change"
        f" — see {log_name}"
    )

    if counts["failed"] > 0:
        return 1
    if counts["no_change"] > 0:
        return 2
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Batch-process SRT files through subtitle_corrector and log results. "
            "Exit 0=clean, 1=failures, 2=no_change files."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python subtitle_pipeline.py inbox/*.srt --output-dir outbox/\n"
            "  python subtitle_pipeline.py ep1.srt ep2.srt --model llama3\n"
            "  python subtitle_pipeline.py ep.srt --log /tmp/run.log --verbose"
        ),
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Input SRT file(s) to process",
    )
    parser.add_argument(
        "--output-dir",
        metavar="PATH",
        default=None,
        help=(
            "Directory to write corrected SRT files. "
            "Default: same directory as input, with .corrected.srt suffix."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Ollama model name (overrides MODEL env var; default: mistral)",
    )
    parser.add_argument(
        "--log",
        metavar="PATH",
        default=DEFAULT_LOG_PATH,
        help=f"JSON lines pipeline log path (default: {DEFAULT_LOG_PATH})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        metavar="N",
        help="Cues per Ollama API call (default: 20)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        metavar="S",
        help="Per-request Ollama timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each drift-reverted cue to stdout",
    )
    parser.add_argument(
        "--drift-log",
        metavar="PATH",
        default=None,
        help="Append drift events as JSON lines to this file",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    input_files: List[Path] = []
    for raw in args.files:
        p = Path(raw)
        if not p.exists():
            logger.error("File not found: %s", raw)
            sys.exit(1)
        if not p.is_file():
            logger.error("Not a file: %s", raw)
            sys.exit(1)
        input_files.append(p)

    output_dir = Path(args.output_dir) if args.output_dir else None
    model = args.model or os.environ.get("MODEL", "mistral")

    exit_code = run_pipeline(
        input_files=input_files,
        output_dir=output_dir,
        model=model,
        log_path=args.log,
        batch_size=args.batch_size,
        timeout=args.timeout,
        verbose=args.verbose,
        drift_log=args.drift_log,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
