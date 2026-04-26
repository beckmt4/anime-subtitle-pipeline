"""core.benchmark — candidate comparison and quality metrics.

Measures subtitle quality by comparing candidates to a reference using
WER, BLEU, and chrF.
The root-level ``compare_core.py`` is now a re-export shim pointing here.

Public API
----------
compute_metrics(ref_texts, cand_texts) → dict   WER / BLEU / chrF
align_segments(ref, cand)              → list   temporally aligned pairs
compare_candidates(ref, cand)          → dict   full comparison report
compute_overlap(seg1, seg2)            → float
"""

from __future__ import annotations

import logging
from typing import List, Tuple, Dict, Any

from core.subtitles import Segment, SubtitleCandidate

logger = logging.getLogger(__name__)


def compute_overlap(seg1: Segment, seg2: Segment) -> float:
    """Compute time overlap in seconds between two segments."""
    start = max(seg1.start, seg2.start)
    end = min(seg1.end, seg2.end)
    return max(0.0, end - start)


def align_segments(
    ref: SubtitleCandidate,
    cand: SubtitleCandidate,
) -> List[Tuple[Segment, Segment]]:
    """Align segments from two candidates based on maximum time overlap."""
    if not ref.segments:
        logger.warning(f"Reference candidate {ref.id} has no segments")
        return []

    if not cand.segments:
        logger.warning(f"Candidate {cand.id} has no segments; alignment impossible")
        return []

    aligned = []
    for ref_seg in ref.segments:
        best_cand_seg = None
        best_overlap = 0.0
        for cand_seg in cand.segments:
            overlap = compute_overlap(ref_seg, cand_seg)
            if overlap > best_overlap:
                best_overlap = overlap
                best_cand_seg = cand_seg

        if best_cand_seg is not None:
            aligned.append((ref_seg, best_cand_seg))
        else:
            logger.debug(f"No overlap for ref segment [{ref_seg.start:.2f}-{ref_seg.end:.2f}]")
            ref_mid = (ref_seg.start + ref_seg.end) / 2
            closest = min(cand.segments, key=lambda s: abs((s.start + s.end) / 2 - ref_mid))
            aligned.append((ref_seg, closest))

    logger.info("Aligned %d segment pairs between %s and %s", len(aligned), ref.id, cand.id)
    return aligned


def compute_metrics(ref_texts: List[str], cand_texts: List[str]) -> Dict[str, float]:
    """Compute WER, BLEU, and chrF between reference and candidate text lists."""
    if len(ref_texts) != len(cand_texts):
        raise ValueError(
            f"Reference and candidate text lists must have same length: "
            f"{len(ref_texts)} vs {len(cand_texts)}"
        )

    if not ref_texts:
        logger.warning("Empty text lists provided; returning zero metrics")
        return {"wer": 0.0, "bleu": 0.0, "chrf": 0.0}

    try:
        import jiwer
        import sacrebleu
    except ImportError as e:
        logger.error(f"Metric library not available: {e}")
        raise

    try:
        wer = jiwer.wer(ref_texts, cand_texts)
    except Exception as e:
        logger.warning(f"WER computation failed: {e}; setting to 1.0")
        wer = 1.0

    try:
        bleu_score = sacrebleu.corpus_bleu(cand_texts, [ref_texts]).score
    except Exception as e:
        logger.warning(f"BLEU computation failed: {e}; setting to 0.0")
        bleu_score = 0.0

    try:
        chrf_score = sacrebleu.corpus_chrf(cand_texts, [ref_texts]).score
    except Exception as e:
        logger.warning(f"chrF computation failed: {e}; setting to 0.0")
        chrf_score = 0.0

    return {
        "wer": round(wer, 4),
        "bleu": round(bleu_score, 2),
        "chrf": round(chrf_score, 2),
    }


def compare_candidates(
    ref: SubtitleCandidate,
    cand: SubtitleCandidate,
    diff_threshold: int = 5,
) -> Dict[str, Any]:
    """Compare two SubtitleCandidates and return detailed metrics."""
    logger.info(f"Comparing candidates: {ref.id} (ref) vs {cand.id} (cand)")

    aligned_pairs = align_segments(ref, cand)

    if not aligned_pairs:
        logger.warning("No aligned pairs; returning empty comparison")
        return {
            "ref_id": ref.id,
            "cand_id": cand.id,
            "metrics": {"wer": 1.0, "bleu": 0.0, "chrf": 0.0},
            "num_segments": 0,
            "num_diffs": 0,
            "diffs": [],
        }

    ref_texts = [r.text.strip() for r, c in aligned_pairs]
    cand_texts = [c.text.strip() for r, c in aligned_pairs]
    metrics = compute_metrics(ref_texts, cand_texts)

    diffs = []
    for ref_seg, cand_seg in aligned_pairs:
        ref_text = ref_seg.text.strip()
        cand_text = cand_seg.text.strip()
        if ref_text != cand_text:
            char_diff = abs(len(ref_text) - len(cand_text))
            if char_diff > diff_threshold or ref_text.lower() != cand_text.lower():
                diffs.append({
                    "start": round(ref_seg.start, 2),
                    "end": round(ref_seg.end, 2),
                    "ref": ref_text,
                    "cand": cand_text,
                })

    logger.info(
        "Comparison complete: %d segments, WER=%.2f%%, BLEU=%.1f, %d text differences",
        len(aligned_pairs), metrics["wer"] * 100, metrics["bleu"], len(diffs),
    )

    return {
        "ref_id": ref.id,
        "cand_id": cand.id,
        "metrics": metrics,
        "num_segments": len(aligned_pairs),
        "num_diffs": len(diffs),
        "diffs": diffs[:20],
    }


__all__ = [
    "align_segments",
    "compute_metrics",
    "compare_candidates",
    "compute_overlap",
]
