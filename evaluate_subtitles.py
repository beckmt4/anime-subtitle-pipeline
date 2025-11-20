"""
Evaluate generated subtitles against reference subtitles.

This CLI aligns generated SRT with a reference (embedded or external)
and computes corpus-level metrics:
 - Match rate
 - chrF++ (sacrebleu)
 - BLEU (sacrebleu)
 - TER (sacrebleu)
 - Avg difflib similarity
 - Avg absolute timing difference

Optionally emits per-segment CSV/JSON and a summary JSON.
"""

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any

import difflib
import sacrebleu

from compare_subtitles import (
    extract_embedded_subtitles,
    parse_srt_file,
    compare_subtitles as run_comparison,
)


logger = logging.getLogger(__name__)


def compute_metrics(preds: List[str], refs: List[str]) -> Dict[str, Any]:
    """Compute corpus-level metrics with sacrebleu and difflib.

    Args:
        preds: list of generated strings
        refs: list of reference strings
    Returns:
        Dict of metrics
    """
    # SacreBLEU metrics
    bleu = sacrebleu.corpus_bleu(preds, [refs])
    chrf = sacrebleu.corpus_chrf(preds, refs)
    ter = sacrebleu.metrics.TER().corpus_score(preds, [refs])

    # difflib average
    diffs = []
    for p, r in zip(preds, refs):
        diffs.append(difflib.SequenceMatcher(None, p, r).ratio())
    avg_diff = sum(diffs) / len(diffs) if diffs else 0.0

    return {
        "bleu": {
            "score": bleu.score,
            "precisions": list(bleu.precisions),
            "bp": bleu.bp,
            "sys_len": bleu.sys_len,
            "ref_len": bleu.ref_len,
        },
        "chrf": {
            "score": chrf.score,
        },
        "ter": {
            "score": ter.score,
        },
        "difflib_similarity_avg": avg_diff * 100.0,
    }


def summarize_from_comparison(comp: Dict[str, Any]) -> Dict[str, Any]:
    """Build a summary from compare_subtitles results plus sacrebleu metrics."""
    matched = [m for m in comp["matches"] if m.get("matched", True)]
    preds = [m["generated_text"] for m in matched]
    refs = [m["reference_text"] for m in matched]

    metrics = compute_metrics(preds, refs) if preds and refs else {}

    # Timing differences
    time_diffs = [abs(m.get("time_diff", 0.0)) for m in matched]
    avg_time_diff = sum(time_diffs) / len(time_diffs) if time_diffs else 0.0

    summary = {
        "segment_counts": {
            "generated": comp.get("generated_count"),
            "reference": comp.get("reference_count"),
            "matched": comp.get("matched_count"),
            "match_rate": comp.get("match_rate"),
        },
        "similarity": {
            "average_similarity": comp.get("average_similarity"),
            "avg_time_diff_seconds": avg_time_diff,
        },
        "metrics": metrics,
    }
    return summary


def save_per_segment(matches: List[Dict[str, Any]], path: Path, as_csv: bool):
    """Save per-segment results to CSV or JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "generated_index",
        "reference_index",
        "similarity",
        "time_diff",
        "generated_text",
        "reference_text",
    ]
    if as_csv:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for m in matches:
                row = {k: m.get(k) for k in fields}
                writer.writerow(row)
    else:
        with open(path, "w", encoding="utf-8") as f:
            for m in matches:
                json.dump({k: m.get(k) for k in fields}, f, ensure_ascii=False)
                f.write("\n")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate generated subtitles against a reference",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use embedded reference track 0
  python evaluate_subtitles.py video.mkv outbox/video.en.srt --subtitle-track 0 --summary results.json --per-segment segments.csv

  # Use external reference SRT
  python evaluate_subtitles.py video.mkv outbox/video.en.srt --reference-srt video.ref.srt --summary results.json
        """
    )

    parser.add_argument("video", type=str, help="Path to source video")
    parser.add_argument("generated_srt", type=str, help="Path to generated SRT")
    parser.add_argument(
        "--subtitle-track",
        type=int,
        default=0,
        help="Reference subtitle track index (default: 0)",
    )
    parser.add_argument(
        "--reference-srt",
        type=str,
        help="External reference SRT (if not using embedded)",
    )
    parser.add_argument(
        "--time-tolerance",
        type=float,
        default=2.0,
        help="Time tolerance in seconds for matching (default: 2.0)",
    )
    parser.add_argument(
        "--summary",
        type=str,
        help="Path to write summary JSON (optional)",
    )
    parser.add_argument(
        "--per-segment",
        type=str,
        help="Path to write per-segment CSV or JSONL (optional; extension determines format)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    video_path = Path(args.video)
    gen_srt = Path(args.generated_srt)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not gen_srt.exists():
        raise FileNotFoundError(f"Generated SRT not found: {gen_srt}")

    # If external reference provided, parse directly. Else extract embedded.
    reference_srt_path = None
    if args.reference_srt:
        reference_srt_path = Path(args.reference_srt)
        if not reference_srt_path.exists():
            raise FileNotFoundError(f"Reference SRT not found: {reference_srt_path}")
    else:
        logger.info("Extracting embedded reference subtitles...")
        reference_srt_path = Path(
            extract_embedded_subtitles(str(video_path), args.subtitle_track, language_filter="eng")
        )

    logger.info("Running alignment and base comparison...")
    comp = run_comparison(
        video_path=str(video_path),
        generated_srt_path=str(gen_srt),
        subtitle_track=args.subtitle_track,
        language_filter="eng",
        time_tolerance=args.time_tolerance,
        output_json_path=None,
        log_level=args.log_level,
        details=False,
    )

    summary = summarize_from_comparison(comp)

    # Output summary JSON if requested
    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logger.info(f"Summary saved to {summary_path}")

    # Output per-segment if requested
    if args.per_segment:
        seg_path = Path(args.per_segment)
        as_csv = seg_path.suffix.lower() == ".csv"
        save_per_segment(comp["matches"], seg_path, as_csv=as_csv)
        logger.info(f"Per-segment results saved to {seg_path}")

    # Print concise report
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    sc = summary["segment_counts"]
    print(f"Generated: {sc['generated']}  Reference: {sc['reference']}  Matched: {sc['matched']} ({sc['match_rate']*100:.1f}%)")
    print(f"Avg similarity (difflib): {summary['metrics'].get('difflib_similarity_avg', 0.0):.1f}%")
    if summary.get("metrics", {}).get("chrf"):
        print(f"chrF++: {summary['metrics']['chrf']['score']:.2f}")
    if summary.get("metrics", {}).get("bleu"):
        print(f"BLEU: {summary['metrics']['bleu']['score']:.2f}")
    if summary.get("metrics", {}).get("ter"):
        print(f"TER: {summary['metrics']['ter']['score']:.2f}")
    print(f"Avg timing diff: {summary['similarity']['avg_time_diff_seconds']:.2f}s")


if __name__ == "__main__":
    main()
