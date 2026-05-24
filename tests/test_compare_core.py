"""Unit tests for compare_core — overlap calculation, segment alignment, metrics."""

from __future__ import annotations

from typing import List
from unittest.mock import MagicMock, patch

import pytest

from core.benchmark.compare_core import compute_overlap, align_segments, compute_metrics
from core.subtitles import Segment, SubtitleCandidate


def make_candidate(id_: str, segs: List[tuple]) -> SubtitleCandidate:
    return SubtitleCandidate(
        id=id_,
        language="en",
        source="test",
        origin_stream="test:0",
        segments=[Segment(s, e, t) for s, e, t in segs],
    )


# ---------------------------------------------------------------------------
# compute_overlap
# ---------------------------------------------------------------------------

class TestComputeOverlap:
    def test_identical_segments_full_overlap(self):
        a = Segment(0.0, 2.0, "A")
        assert compute_overlap(a, a) == pytest.approx(2.0)

    def test_partial_overlap(self):
        a = Segment(0.0, 2.0, "A")
        b = Segment(1.0, 3.0, "B")
        assert compute_overlap(a, b) == pytest.approx(1.0)

    def test_adjacent_segments_no_overlap(self):
        a = Segment(0.0, 1.0, "A")
        b = Segment(1.0, 2.0, "B")
        assert compute_overlap(a, b) == pytest.approx(0.0)

    def test_gap_between_segments_no_overlap(self):
        a = Segment(0.0, 1.0, "A")
        b = Segment(2.0, 3.0, "B")
        assert compute_overlap(a, b) == pytest.approx(0.0)

    def test_one_contained_in_other(self):
        outer = Segment(0.0, 4.0, "outer")
        inner = Segment(1.0, 2.0, "inner")
        assert compute_overlap(outer, inner) == pytest.approx(1.0)
        assert compute_overlap(inner, outer) == pytest.approx(1.0)

    def test_overlap_is_symmetric(self):
        a = Segment(0.0, 1.5, "A")
        b = Segment(1.0, 2.0, "B")
        assert compute_overlap(a, b) == compute_overlap(b, a)

    def test_zero_duration_segment_no_overlap(self):
        point = Segment(1.0, 1.0, "")
        other = Segment(0.0, 2.0, "B")
        assert compute_overlap(point, other) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# align_segments
# ---------------------------------------------------------------------------

class TestAlignSegments:
    def test_each_ref_segment_gets_a_pair(self):
        ref = make_candidate("ref", [(0.0, 2.0, "A"), (2.0, 4.0, "B")])
        cand = make_candidate("cand", [(0.0, 4.0, "AB")])
        pairs = align_segments(ref, cand)
        assert len(pairs) == 2  # one pair per ref segment

    def test_selects_max_overlap_candidate(self):
        ref = make_candidate("ref", [(0.0, 2.0, "A")])
        # first cand overlaps 1 sec, second overlaps 2 sec — second should win
        cand = make_candidate("cand", [(1.0, 2.0, "partial"), (0.0, 2.0, "full")])
        pairs = align_segments(ref, cand)
        # "full" cand (index 1) overlaps for 2.0s vs "partial" (index 0) for 1.0s
        assert pairs[0][1].text == "full"

    def test_empty_ref_returns_empty(self):
        ref = make_candidate("ref", [])
        cand = make_candidate("cand", [(0.0, 1.0, "A")])
        assert align_segments(ref, cand) == []

    def test_empty_cand_returns_empty(self):
        ref = make_candidate("ref", [(0.0, 1.0, "A")])
        cand = make_candidate("cand", [])
        assert align_segments(ref, cand) == []

    def test_no_overlap_falls_back_to_nearest_by_midpoint(self):
        ref = make_candidate("ref", [(0.0, 1.0, "early")])
        cand = make_candidate("cand", [(10.0, 11.0, "far"), (20.0, 21.0, "farther")])
        pairs = align_segments(ref, cand)
        assert len(pairs) == 1
        # ref midpoint = 0.5; cand midpoints are 10.5 and 20.5 — nearest is "far"
        assert pairs[0][1].text == "far"

    def test_result_pairs_contain_ref_and_cand_segments(self):
        ref = make_candidate("ref", [(0.0, 1.0, "R")])
        cand = make_candidate("cand", [(0.0, 1.0, "C")])
        pairs = align_segments(ref, cand)
        ref_seg, cand_seg = pairs[0]
        assert ref_seg.text == "R"
        assert cand_seg.text == "C"


# ---------------------------------------------------------------------------
# compute_metrics — mocked jiwer / sacrebleu to avoid CI dependency
# ---------------------------------------------------------------------------

class TestComputeMetrics:
    def test_empty_lists_return_zero_metrics(self):
        result = compute_metrics([], [])
        assert result == {"wer": 0.0, "bleu": 0.0, "chrf": 0.0}

    def test_mismatched_lengths_raise_value_error(self):
        with pytest.raises(ValueError, match="same length"):
            compute_metrics(["a", "b"], ["a"])

    def test_returns_expected_metric_keys(self):
        mock_jiwer = MagicMock()
        mock_jiwer.wer.return_value = 0.25

        bleu_result = MagicMock()
        bleu_result.score = 75.5
        chrf_result = MagicMock()
        chrf_result.score = 80.2
        mock_sacrebleu = MagicMock()
        mock_sacrebleu.corpus_bleu.return_value = bleu_result
        mock_sacrebleu.corpus_chrf.return_value = chrf_result

        with patch.dict("sys.modules", {"jiwer": mock_jiwer, "sacrebleu": mock_sacrebleu}):
            result = compute_metrics(["hello world"], ["hello there"])

        assert set(result.keys()) == {"wer", "bleu", "chrf"}
        assert result["wer"] == pytest.approx(0.25)
        assert result["bleu"] == pytest.approx(75.5)
        assert result["chrf"] == pytest.approx(80.2)

    def test_wer_called_with_ref_and_cand(self):
        mock_jiwer = MagicMock()
        mock_jiwer.wer.return_value = 0.0
        mock_sacrebleu = MagicMock()
        mock_sacrebleu.corpus_bleu.return_value = MagicMock(score=100.0)
        mock_sacrebleu.corpus_chrf.return_value = MagicMock(score=100.0)

        refs = ["hello"]
        cands = ["hello"]
        with patch.dict("sys.modules", {"jiwer": mock_jiwer, "sacrebleu": mock_sacrebleu}):
            compute_metrics(refs, cands)

        mock_jiwer.wer.assert_called_once_with(refs, cands)
