"""Core comparison module for benchmarking subtitle candidates.

This module provides:
- Temporal alignment of subtitle segments based on overlap
- Text quality metrics (WER, BLEU, chrF)
- Comparison function for SubtitleCandidate objects
"""

import logging
from typing import List, Tuple, Dict, Any

from models import SubtitleCandidate, Segment

logger = logging.getLogger(__name__)


def compute_overlap(seg1: Segment, seg2: Segment) -> float:
    """Compute time overlap in seconds between two segments.
    
    Args:
        seg1: First segment
        seg2: Second segment
        
    Returns:
        Overlap duration in seconds (0 if no overlap)
    """
    start = max(seg1.start, seg2.start)
    end = min(seg1.end, seg2.end)
    return max(0.0, end - start)


def align_segments(
    ref: SubtitleCandidate,
    cand: SubtitleCandidate
) -> List[Tuple[Segment, Segment]]:
    """Align segments from two candidates based on maximum time overlap.
    
    For each reference segment, finds the candidate segment with the
    greatest time overlap. This creates a many-to-one mapping where
    multiple reference segments may align to the same candidate segment.
    
    Args:
        ref: Reference SubtitleCandidate
        cand: Candidate SubtitleCandidate to align
        
    Returns:
        List of (ref_segment, cand_segment) pairs, one per reference segment
        
    Example:
        >>> ref = SubtitleCandidate(..., segments=[Segment(0, 2, "A"), Segment(2, 4, "B")])
        >>> cand = SubtitleCandidate(..., segments=[Segment(0, 3, "AB"), Segment(3, 4, "C")])
        >>> pairs = align_segments(ref, cand)
        >>> # Returns: [(Segment(0,2,"A"), Segment(0,3,"AB")), (Segment(2,4,"B"), Segment(0,3,"AB"))]
    """
    if not ref.segments:
        logger.warning(f"Reference candidate {ref.id} has no segments")
        return []
    
    if not cand.segments:
        logger.warning(f"Candidate {cand.id} has no segments; alignment impossible")
        return []
    
    aligned = []
    
    for ref_seg in ref.segments:
        # Find candidate segment with maximum overlap
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
            # No overlap found; pair with nearest candidate segment
            logger.debug(f"No overlap for ref segment [{ref_seg.start:.2f}-{ref_seg.end:.2f}]")
            # Find closest by midpoint distance
            ref_mid = (ref_seg.start + ref_seg.end) / 2
            closest = min(
                cand.segments,
                key=lambda s: abs((s.start + s.end) / 2 - ref_mid)
            )
            aligned.append((ref_seg, closest))
    
    logger.info(
        f"Aligned {len(aligned)} segment pairs between {ref.id} and {cand.id}"
    )
    
    return aligned


def compute_metrics(ref_texts: List[str], cand_texts: List[str]) -> Dict[str, float]:
    """Compute text quality metrics between reference and candidate texts.
    
    Metrics computed:
    - WER: Word Error Rate (lower is better, 0.0 = perfect)
    - BLEU: BLEU score (higher is better, 100.0 = perfect)
    - chrF: Character F-score (higher is better, 100.0 = perfect)
    
    Args:
        ref_texts: List of reference text strings
        cand_texts: List of candidate text strings (same length as ref_texts)
        
    Returns:
        Dictionary with metric names and values
        
    Raises:
        ValueError: If input lists have different lengths
    """
    if len(ref_texts) != len(cand_texts):
        raise ValueError(
            f"Reference and candidate text lists must have same length: "
            f"{len(ref_texts)} vs {len(cand_texts)}"
        )
    
    if not ref_texts:
        logger.warning("Empty text lists provided; returning zero metrics")
        return {"wer": 0.0, "bleu": 0.0, "chrf": 0.0}
    
    # Import metric libraries (lazy import to avoid startup cost if not used)
    try:
        import jiwer
        import sacrebleu
    except ImportError as e:
        logger.error(f"Metric library not available: {e}")
        logger.error("Install with: pip install jiwer sacrebleu")
        raise
    
    # Compute WER (Word Error Rate)
    # jiwer expects reference and hypothesis strings or lists
    try:
        wer = jiwer.wer(ref_texts, cand_texts)
    except Exception as e:
        logger.warning(f"WER computation failed: {e}; setting to 1.0")
        wer = 1.0
    
    # Compute BLEU score
    # sacrebleu expects: hypotheses (list), references (list of lists)
    try:
        bleu = sacrebleu.corpus_bleu(
            cand_texts,
            [ref_texts]  # references must be list of lists
        )
        bleu_score = bleu.score  # 0-100 scale
    except Exception as e:
        logger.warning(f"BLEU computation failed: {e}; setting to 0.0")
        bleu_score = 0.0
    
    # Compute chrF (character F-score)
    try:
        chrf = sacrebleu.corpus_chrf(
            cand_texts,
            [ref_texts]
        )
        chrf_score = chrf.score  # 0-100 scale
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
    diff_threshold: int = 5
) -> Dict[str, Any]:
    """Compare two SubtitleCandidates and return detailed metrics.
    
    Aligns segments temporally, computes text metrics, and identifies
    segments with differing text.
    
    Args:
        ref: Reference SubtitleCandidate (ground truth)
        cand: Candidate SubtitleCandidate to evaluate
        diff_threshold: Minimum character difference to consider segments different
        
    Returns:
        Dictionary containing:
        - ref_id: ID of reference candidate
        - cand_id: ID of candidate being evaluated
        - metrics: Dict with wer, bleu, chrf scores
        - num_segments: Number of aligned segment pairs
        - num_diffs: Number of segments with text differences
        - diffs: List of dicts with start, end, ref_text, cand_text for differing segments
        
    Example:
        >>> result = compare_candidates(embedded_en, asr_en)
        >>> print(f"WER: {result['metrics']['wer']:.2%}")
        >>> print(f"BLEU: {result['metrics']['bleu']:.1f}/100")
    """
    logger.info(f"Comparing candidates: {ref.id} (ref) vs {cand.id} (cand)")
    
    # Align segments
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
    
    # Extract text lists
    ref_texts = [r.text.strip() for r, c in aligned_pairs]
    cand_texts = [c.text.strip() for r, c in aligned_pairs]
    
    # Compute metrics
    metrics = compute_metrics(ref_texts, cand_texts)
    
    # Identify differing segments
    diffs = []
    for ref_seg, cand_seg in aligned_pairs:
        ref_text = ref_seg.text.strip()
        cand_text = cand_seg.text.strip()
        
        # Simple difference check: character-level edit distance or threshold
        if ref_text != cand_text:
            # Use Levenshtein-like heuristic: if diff is significant
            char_diff = abs(len(ref_text) - len(cand_text))
            if char_diff > diff_threshold or ref_text.lower() != cand_text.lower():
                diffs.append({
                    "start": round(ref_seg.start, 2),
                    "end": round(ref_seg.end, 2),
                    "ref": ref_text,
                    "cand": cand_text,
                })
    
    result = {
        "ref_id": ref.id,
        "cand_id": cand.id,
        "metrics": metrics,
        "num_segments": len(aligned_pairs),
        "num_diffs": len(diffs),
        "diffs": diffs[:20],  # Limit to first 20 diffs for readability
    }
    
    logger.info(
        f"Comparison complete: {len(aligned_pairs)} segments, "
        f"WER={metrics['wer']:.2%}, BLEU={metrics['bleu']:.1f}, "
        f"{len(diffs)} text differences"
    )
    
    return result


__all__ = [
    "align_segments",
    "compute_metrics",
    "compare_candidates",
    "compute_overlap",
]
