"""Tests for benchmark comparison functionality."""
import os
import pytest

# Skip the entire module if optional metric libraries are not installed
pytest.importorskip("jiwer")
pytest.importorskip("sacrebleu")

from core.subtitles import Segment, SubtitleCandidate
from core.benchmark.compare_core import align_segments, compute_metrics, compare_candidates, compute_overlap


def test_compute_overlap():
    """Test time overlap calculation between segments."""
    # Perfect overlap
    seg1 = Segment(start=1.0, end=3.0, text="A")
    seg2 = Segment(start=1.0, end=3.0, text="B")
    assert compute_overlap(seg1, seg2) == 2.0
    
    # Partial overlap
    seg1 = Segment(start=1.0, end=3.0, text="A")
    seg2 = Segment(start=2.0, end=4.0, text="B")
    assert compute_overlap(seg1, seg2) == 1.0
    
    # No overlap
    seg1 = Segment(start=1.0, end=2.0, text="A")
    seg2 = Segment(start=3.0, end=4.0, text="B")
    assert compute_overlap(seg1, seg2) == 0.0
    
    # seg1 contains seg2
    seg1 = Segment(start=1.0, end=5.0, text="A")
    seg2 = Segment(start=2.0, end=3.0, text="B")
    assert compute_overlap(seg1, seg2) == 1.0
    
    print("✓ Overlap computation tests passed")


def test_align_segments_perfect():
    """Test alignment with perfect timing correspondence."""
    ref_segs = [
        Segment(start=0.0, end=2.0, text="Hello"),
        Segment(start=2.0, end=4.0, text="World"),
    ]
    cand_segs = [
        Segment(start=0.0, end=2.0, text="Hi"),
        Segment(start=2.0, end=4.0, text="Earth"),
    ]
    
    ref = SubtitleCandidate(
        id="ref", language="en", source="embedded",
        origin_stream="s:0", segments=ref_segs, meta={}
    )
    cand = SubtitleCandidate(
        id="cand", language="en", source="asr",
        origin_stream="a:0", segments=cand_segs, meta={}
    )
    
    pairs = align_segments(ref, cand)
    
    assert len(pairs) == 2
    assert pairs[0][0].text == "Hello"
    assert pairs[0][1].text == "Hi"
    assert pairs[1][0].text == "World"
    assert pairs[1][1].text == "Earth"
    
    print("✓ Perfect alignment test passed")


def test_align_segments_many_to_one():
    """Test alignment where multiple ref segments map to one candidate."""
    ref_segs = [
        Segment(start=0.0, end=1.0, text="A"),
        Segment(start=1.0, end=2.0, text="B"),
        Segment(start=2.0, end=3.0, text="C"),
    ]
    cand_segs = [
        Segment(start=0.0, end=2.5, text="AB"),  # Spans first two
        Segment(start=2.5, end=4.0, text="D"),
    ]
    
    ref = SubtitleCandidate(
        id="ref", language="en", source="embedded",
        origin_stream="s:0", segments=ref_segs, meta={}
    )
    cand = SubtitleCandidate(
        id="cand", language="en", source="asr",
        origin_stream="a:0", segments=cand_segs, meta={}
    )
    
    pairs = align_segments(ref, cand)
    
    assert len(pairs) == 3
    # First two ref segments should align to first candidate segment
    assert pairs[0][0].text == "A"
    assert pairs[0][1].text == "AB"
    assert pairs[1][0].text == "B"
    assert pairs[1][1].text == "AB"
    # Third ref segment aligns to second candidate (partial overlap)
    assert pairs[2][0].text == "C"
    # Could be either AB or D depending on overlap; just check it exists
    assert pairs[2][1] is not None
    
    print("✓ Many-to-one alignment test passed")


def test_compute_metrics_perfect():
    """Test metrics with identical text."""
    ref_texts = ["Hello world", "How are you"]
    cand_texts = ["Hello world", "How are you"]
    
    metrics = compute_metrics(ref_texts, cand_texts)
    
    assert metrics["wer"] == 0.0, f"Expected WER=0.0, got {metrics['wer']}"
    # BLEU can be 0 for short texts due to n-gram requirements; just check it's valid
    assert 0 <= metrics["bleu"] <= 100.0, f"BLEU out of range: {metrics['bleu']}"
    assert metrics["chrf"] >= 95.0, f"Expected high chrF, got {metrics['chrf']}"
    
    print("✓ Perfect match metrics test passed")


def test_compute_metrics_different():
    """Test metrics with different text."""
    ref_texts = ["The cat sat on the mat"]
    cand_texts = ["A dog stood near a rug"]
    
    metrics = compute_metrics(ref_texts, cand_texts)
    
    # Should have high WER (all words different)
    assert metrics["wer"] > 0.5, f"Expected high WER, got {metrics['wer']}"
    # Should have low BLEU (no matching n-grams)
    assert metrics["bleu"] < 20.0, f"Expected low BLEU, got {metrics['bleu']}"
    # chrF should be moderate (some character overlap)
    assert 0 <= metrics["chrf"] <= 100, f"chrF out of range: {metrics['chrf']}"
    
    print("✓ Different text metrics test passed")


def test_compare_candidates_basic():
    """Test full comparison workflow."""
    ref_segs = [
        Segment(start=0.0, end=2.0, text="Hello there"),
        Segment(start=2.5, end=4.0, text="Nice weather today"),
    ]
    cand_segs = [
        Segment(start=0.0, end=2.0, text="Hey there"),
        Segment(start=2.5, end=4.0, text="Beautiful day today"),
    ]
    
    ref = SubtitleCandidate(
        id="embedded_en", language="en", source="embedded",
        origin_stream="s:2", segments=ref_segs, meta={}
    )
    cand = SubtitleCandidate(
        id="en_asr", language="en", source="asr",
        origin_stream="a:1", segments=cand_segs, meta={}
    )
    
    result = compare_candidates(ref, cand)
    
    assert result["ref_id"] == "embedded_en"
    assert result["cand_id"] == "en_asr"
    assert result["num_segments"] == 2
    assert "metrics" in result
    assert "wer" in result["metrics"]
    assert "bleu" in result["metrics"]
    assert "chrf" in result["metrics"]
    assert result["num_diffs"] >= 0
    assert isinstance(result["diffs"], list)
    
    # Should detect text differences
    assert result["num_diffs"] > 0, "Expected differences between 'Hello' vs 'Hey', etc."
    
    print("✓ Basic comparison test passed")
    print(f"  WER: {result['metrics']['wer']:.2%}")
    print(f"  BLEU: {result['metrics']['bleu']:.1f}")
    print(f"  chrF: {result['metrics']['chrf']:.1f}")
    print(f"  Diffs: {result['num_diffs']}")


def run_all_tests():
    """Run all benchmark tests."""
    print("Running benchmark comparison tests...\n")
    
    test_compute_overlap()
    test_align_segments_perfect()
    test_align_segments_many_to_one()
    test_compute_metrics_perfect()
    test_compute_metrics_different()
    test_compare_candidates_basic()
    
    print("\n✅ All benchmark tests PASSED")


if __name__ == "__main__":
    # Disable tracing for tests
    os.environ.setdefault("TRACING_ENABLED", "false")
    run_all_tests()
