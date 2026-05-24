"""CLI tool: compare two SRT files and report WER / BLEU / chrF.

Usage:
    python compare_srt.py REF.srt CAND.srt [--diffs N] [--quiet]

Examples:
    # Quick quality check of a generated SRT against ground truth
    python compare_srt.py ground_truth.en.srt outbox/video.en.srt

    # Compare raw-MT vs LLM-polished output on the same clip
    python compare_srt.py outbox/video.raw.srt outbox/video.llm.srt --diffs 10

The reference SRT should be the higher-quality or ground-truth one.
Built on top of compare_core.compare_candidates; kept dependency-light so
it can be run without loading faster_whisper / torch / transformers.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import List

from core.subtitles import Segment, SubtitleCandidate
from core.benchmark import compare_candidates


_TS_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,\.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,\.](\d{3})"
)


def _ts_to_seconds(h: int, m: int, s: int, ms: int) -> float:
    return h * 3600 + m * 60 + s + ms / 1000.0


def parse_srt(path: Path) -> List[Segment]:
    """Parse an SRT file into a list of Segments.

    Standalone parser so this tool does not pull in the heavy ASR/torch stack
    that srt_writer.read_srt_file drags in transitively.
    """
    if not path.exists():
        raise FileNotFoundError(f"SRT not found: {path}")

    content = path.read_text(encoding="utf-8-sig")  # tolerate BOM
    segments: List[Segment] = []
    for block in re.split(r"\r?\n\r?\n", content.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        # Find the timestamp line (usually line 1, but be tolerant)
        ts_line = None
        text_start = None
        for i, ln in enumerate(lines):
            m = _TS_RE.search(ln)
            if m:
                ts_line = m
                text_start = i + 1
                break
        if ts_line is None or text_start is None or text_start >= len(lines):
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, ts_line.groups())
        start = _ts_to_seconds(h1, m1, s1, ms1)
        end = _ts_to_seconds(h2, m2, s2, ms2)
        text = " ".join(lines[text_start:]).strip()
        if not text:
            continue
        segments.append(Segment(start=start, end=end, text=text))
    return segments


def srt_to_candidate(path: Path, candidate_id: str) -> SubtitleCandidate:
    segs = parse_srt(path)
    return SubtitleCandidate(
        id=candidate_id,
        language="en",
        source="srt",
        origin_stream=str(path.name),
        segments=segs,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare two SRT files with WER / BLEU / chrF.",
    )
    parser.add_argument("ref", help="Reference SRT (ground truth / higher-quality)")
    parser.add_argument("cand", help="Candidate SRT to evaluate")
    parser.add_argument(
        "--diffs", type=int, default=5,
        help="How many segment-level diffs to print (default: 5, 0 to suppress)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress info logs from the comparison engine",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    ref_path = Path(args.ref)
    cand_path = Path(args.cand)

    ref = srt_to_candidate(ref_path, candidate_id=f"ref:{ref_path.name}")
    cand = srt_to_candidate(cand_path, candidate_id=f"cand:{cand_path.name}")

    if not ref.segments:
        print(f"ERROR: reference SRT parsed to 0 segments: {ref_path}", file=sys.stderr)
        return 2
    if not cand.segments:
        print(f"ERROR: candidate SRT parsed to 0 segments: {cand_path}", file=sys.stderr)
        return 2

    print(f"Reference : {ref_path}  ({len(ref.segments)} segments)")
    print(f"Candidate : {cand_path}  ({len(cand.segments)} segments)")
    print()

    result = compare_candidates(ref, cand)
    m = result["metrics"]
    # WER: lower is better.  BLEU / chrF: higher is better.
    print(f"WER  : {m['wer']:.4f}   (lower is better, 0 = perfect)")
    print(f"BLEU : {m['bleu']:.2f}   (0-100, higher is better)")
    print(f"chrF : {m['chrf']:.2f}   (0-100, higher is better)")
    print(f"Aligned pairs: {result['num_segments']}   Diffs: {result['num_diffs']}")

    if args.diffs > 0 and result["diffs"]:
        print()
        print(f"First {min(args.diffs, len(result['diffs']))} diffs:")
        for d in result["diffs"][: args.diffs]:
            print(f"  [{d['start']:7.2f} → {d['end']:7.2f}]")
            print(f"    REF : {d['ref']}")
            print(f"    CAND: {d['cand']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
