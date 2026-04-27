"""Tests for benchmark hardening — covers all 5 child issues of the EPIC.

Child #1  Clean up benchmark config handling  → test_benchmark_config_*
Child #2  Benchmark result persistence        → test_persistence_*
Child #3  Candidate scorecards                → test_scorecards_*
Child #4  HTML report renderer                → test_html_report_*
Child #5  Regression test fixtures            → test_regression_*
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

# ---------------------------------------------------------------------------
# Fixture loading helper
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "benchmark"
_SMALL_FIXTURE = _FIXTURE_DIR / "benchmark_results_small.json"


def _load_fixture(name: str = "benchmark_results_small.json") -> Dict[str, Any]:
    with open(_FIXTURE_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


# ===========================================================================
# Child #1 — Clean up benchmark config handling
# ===========================================================================

class TestBenchmarkConfig:
    """BenchmarkConfig reads all benchmark settings from Config in one place."""

    def test_defaults_when_no_benchmark_section(self):
        from config import Config
        from core.benchmark.config import BenchmarkConfig, DEFAULT_REFERENCE_PRIORITY

        cfg = Config()
        # Remove benchmark section entirely if present
        cfg._config.pop("benchmark", None)

        bc = BenchmarkConfig.from_config(cfg)

        assert bc.use_embedded_en is True
        assert bc.use_embedded_jp is True
        assert bc.use_en_audio is True
        assert bc.use_ja_audio is True
        assert bc.compare_all_pairs is False
        assert bc.max_diffs_per_comparison == 20
        assert bc.reference_priority == DEFAULT_REFERENCE_PRIORITY
        assert bc.translation_engines == ["marian"]

    def test_sources_flags_respected(self):
        from config import Config
        from core.benchmark.config import BenchmarkConfig

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {
                "use_embedded_en": False,
                "use_embedded_jp": True,
                "use_en_audio": False,
                "use_ja_audio": True,
            }
        }
        bc = BenchmarkConfig.from_config(cfg)

        assert bc.use_embedded_en is False
        assert bc.use_embedded_jp is True
        assert bc.use_en_audio is False
        assert bc.use_ja_audio is True

    def test_compare_all_pairs_and_max_diffs(self):
        from config import Config
        from core.benchmark.config import BenchmarkConfig

        cfg = Config()
        cfg._config["benchmark"] = {
            "compare_all_pairs": True,
            "max_diffs_per_comparison": 5,
        }
        bc = BenchmarkConfig.from_config(cfg)

        assert bc.compare_all_pairs is True
        assert bc.max_diffs_per_comparison == 5

    def test_reference_priority_overridden(self):
        from config import Config
        from core.benchmark.config import BenchmarkConfig

        cfg = Config()
        custom_priority = ["en_audio_asr", "embedded_en"]
        cfg._config["benchmark"] = {"reference_priority": custom_priority}
        bc = BenchmarkConfig.from_config(cfg)

        assert bc.reference_priority == custom_priority

    def test_translation_engines_from_benchmark_section(self):
        from config import Config
        from core.benchmark.config import BenchmarkConfig

        cfg = Config()
        cfg._config["benchmark"] = {"translation_engines": ["marian", "llm_direct"]}
        bc = BenchmarkConfig.from_config(cfg)

        assert bc.translation_engines == ["marian", "llm_direct"]

    def test_translation_engines_fallback_to_translation_section(self):
        from config import Config
        from core.benchmark.config import BenchmarkConfig

        cfg = Config()
        cfg._config.pop("benchmark", None)
        cfg._config.setdefault("translation", {})["engine"] = "hybrid"
        bc = BenchmarkConfig.from_config(cfg)

        assert bc.translation_engines == ["hybrid"]

    def test_translation_engines_string_normalised_to_list(self):
        from config import Config
        from core.benchmark.config import BenchmarkConfig

        cfg = Config()
        cfg._config["benchmark"] = {"translation_engines": "llm_direct"}
        bc = BenchmarkConfig.from_config(cfg)

        assert bc.translation_engines == ["llm_direct"]

    def test_dataclass_fields_immutable_default_lists(self):
        """Two BenchmarkConfig instances must not share the same default list."""
        from core.benchmark.config import BenchmarkConfig

        bc1 = BenchmarkConfig()
        bc2 = BenchmarkConfig()
        bc1.reference_priority.append("extra")
        assert "extra" not in bc2.reference_priority


# ===========================================================================
# Child #2 — Benchmark result persistence
# ===========================================================================

class TestBenchmarkPersistence:
    """Benchmark comparisons are stored in ArtifactRegistry when provided."""

    def _make_registry(self):
        from core.artifacts import ArtifactRegistry
        return ArtifactRegistry(db_path=":memory:")

    def test_run_benchmark_persists_comparisons(self, tmp_path, monkeypatch):
        """run_benchmark stores one BenchmarkRunRecord per comparison."""
        pytest.importorskip("jiwer")
        pytest.importorskip("sacrebleu")

        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, AudioStream, SubtitleStream

        synth_media = MediaInfo(
            path=Path("dummy.mkv"),
            format_name="matroska",
            duration=30.0,
            audio_streams=[AudioStream(index=0, codec="aac", language="en", raw_language="eng")],
            subtitle_streams=[
                SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng"),
            ],
        )

        def _fake_segs(prefix):
            return [Segment(start=0.0, end=1.0, text=f"{prefix} one"),
                    Segment(start=1.0, end=2.0, text=f"{prefix} two")]

        def _fake_extract_subtitle_track(video, sub_index, language, output_dir=None):
            return SubtitleCandidate(
                id=f"embedded_{language}_s{sub_index}",
                language=language, source="embedded",
                origin_stream=f"sub:{sub_index}",
                segments=_fake_segs(f"emb_{language}"), meta={},
            )

        def _fake_extract_audio(_v, _o, _n):
            Path(_o).write_bytes(b"")

        class _FakeASR:
            def __init__(self, _c): pass
            def transcribe_audio_to_segments(self, _p, language):
                return _fake_segs(f"asr_{language}"), None

        def _fake_build_candidate(segs, cfg, candidate_id, language, origin_stream):
            return SubtitleCandidate(id=candidate_id, language=language,
                                     source="asr", origin_stream=origin_stream,
                                     segments=segs, meta={})

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth_media)
        monkeypatch.setattr(bm, "extract_subtitle_track", _fake_extract_subtitle_track)
        monkeypatch.setattr(bm, "extract_audio_with_ffmpeg", _fake_extract_audio)
        monkeypatch.setattr(bm, "FasterWhisperASR", _FakeASR)
        monkeypatch.setattr(bm, "build_candidate_from_segments", _fake_build_candidate)

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {"use_embedded_en": True, "use_embedded_jp": False,
                        "use_en_audio": True, "use_ja_audio": False},
            "compare_all_pairs": False,
        }

        dummy_video = tmp_path / "ep01.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        registry = self._make_registry()
        results = bm.run_benchmark(
            str(dummy_video), cfg, use_llm=False,
            output_dir=str(tmp_path), registry=registry,
        )

        # Should have persisted one record per comparison
        from core.artifacts.pipeline_wiring import compute_media_hash
        actual_hash = compute_media_hash(dummy_video)
        stored_runs = registry.list_benchmark_runs(actual_hash)
        assert len(stored_runs) == len(results["comparisons"]), (
            f"Expected {len(results['comparisons'])} stored runs, "
            f"got {len(stored_runs)}"
        )

    def test_run_benchmark_without_registry_does_not_raise(self, tmp_path, monkeypatch):
        """registry=None must not break the pipeline."""
        pytest.importorskip("jiwer")
        pytest.importorskip("sacrebleu")

        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, AudioStream, SubtitleStream

        synth = MediaInfo(
            path=Path("x.mkv"), format_name="matroska", duration=10.0,
            audio_streams=[AudioStream(index=0, codec="aac", language="en", raw_language="eng")],
            subtitle_streams=[SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng")],
        )

        def _segs(p):
            return [Segment(start=0.0, end=1.0, text=f"{p} a")]

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth)
        monkeypatch.setattr(bm, "extract_subtitle_track",
                            lambda v, i, language, output_dir=None: SubtitleCandidate(
                                id=f"embedded_{language}_s{i}", language=language,
                                source="embedded", origin_stream=f"sub:{i}",
                                segments=_segs(language), meta={}))
        monkeypatch.setattr(bm, "extract_audio_with_ffmpeg", lambda v, o, n: Path(o).write_bytes(b""))

        class _ASR:
            def __init__(self, _c): pass
            def transcribe_audio_to_segments(self, _p, language):
                return _segs(f"asr_{language}"), None

        monkeypatch.setattr(bm, "FasterWhisperASR", _ASR)
        monkeypatch.setattr(bm, "build_candidate_from_segments",
                            lambda segs, cfg, candidate_id, language, origin_stream:
                            SubtitleCandidate(id=candidate_id, language=language,
                                             source="asr", origin_stream=origin_stream,
                                             segments=segs, meta={}))

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {"use_embedded_en": True, "use_embedded_jp": False,
                        "use_en_audio": True, "use_ja_audio": False},
        }

        dummy_video = tmp_path / "ep02.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False,
                                   output_dir=str(tmp_path), registry=None)
        assert "comparisons" in results

    def test_stored_run_metrics_match_comparison(self, tmp_path, monkeypatch):
        """Stored BenchmarkRunRecord metrics equal the comparison metrics."""
        pytest.importorskip("jiwer")
        pytest.importorskip("sacrebleu")

        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, AudioStream, SubtitleStream

        synth = MediaInfo(
            path=Path("x.mkv"), format_name="matroska", duration=10.0,
            audio_streams=[AudioStream(index=0, codec="aac", language="en", raw_language="eng")],
            subtitle_streams=[SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng")],
        )
        segs_ref = [Segment(start=0.0, end=1.0, text="Hello world")]
        segs_cand = [Segment(start=0.0, end=1.0, text="Hi world")]

        call_count = {"n": 0}

        def _fake_extract(v, i, language, output_dir=None):
            call_count["n"] += 1
            s = segs_ref if call_count["n"] == 1 else segs_cand
            return SubtitleCandidate(id=f"embedded_{language}_s{i}", language=language,
                                     source="embedded", origin_stream=f"sub:{i}",
                                     segments=s, meta={})

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth)
        monkeypatch.setattr(bm, "extract_subtitle_track", _fake_extract)
        monkeypatch.setattr(bm, "extract_audio_with_ffmpeg", lambda v, o, n: Path(o).write_bytes(b""))

        class _ASR:
            def __init__(self, _c): pass
            def transcribe_audio_to_segments(self, _p, language):
                return segs_cand, None

        monkeypatch.setattr(bm, "FasterWhisperASR", _ASR)
        monkeypatch.setattr(bm, "build_candidate_from_segments",
                            lambda segs, cfg, candidate_id, language, origin_stream:
                            SubtitleCandidate(id=candidate_id, language=language,
                                             source="asr", origin_stream=origin_stream,
                                             segments=segs, meta={}))

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {"use_embedded_en": True, "use_embedded_jp": False,
                        "use_en_audio": True, "use_ja_audio": False},
        }

        dummy_video = tmp_path / "ep03.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        from core.artifacts import ArtifactRegistry
        registry = ArtifactRegistry(db_path=":memory:")

        results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False,
                                   output_dir=str(tmp_path), registry=registry)

        if results["comparisons"]:
            from core.artifacts.pipeline_wiring import compute_media_hash
            actual_hash = compute_media_hash(dummy_video)
            stored = registry.list_benchmark_runs(actual_hash)
            assert len(stored) == len(results["comparisons"])
            stored_wers = {r.wer for r in stored}
            expected_wers = {c["metrics"]["wer"] for c in results["comparisons"]}
            assert stored_wers == expected_wers


# ===========================================================================
# Child #3 — Candidate scorecards
# ===========================================================================

class TestCandidateScorecards:
    """build_scorecards produces per-candidate summaries ranked by quality."""

    def test_scorecards_present_in_fixture(self):
        data = _load_fixture()
        assert "scorecards" in data
        assert len(data["scorecards"]) == len(data["candidates"])

    def test_reference_scorecard_ranked_ref(self):
        from core.benchmark.html_report import build_scorecards

        data = _load_fixture()
        scorecards = build_scorecards(data)

        ref_sc = next(sc for sc in scorecards if sc["is_reference"])
        assert ref_sc["rank"] == "REF"
        assert ref_sc["id"] == data["reference_id"]

    def test_non_reference_ranked_by_composite(self):
        from core.benchmark.html_report import build_scorecards

        data = _load_fixture()
        scorecards = build_scorecards(data)

        non_ref = [sc for sc in scorecards if not sc["is_reference"]]
        ranks = [sc["rank"] for sc in non_ref]
        assert ranks == sorted(ranks), "Non-reference scorecards must be in rank order"

        composites = [sc["composite_score"] for sc in non_ref]
        assert composites == sorted(composites, reverse=True), (
            "Better composite score should have lower (better) rank number"
        )

    def test_scorecard_metrics_match_comparison(self):
        from core.benchmark.html_report import build_scorecards

        data = _load_fixture()
        scorecards = build_scorecards(data)

        for comp in data["comparisons"]:
            cid = comp["cand_id"]
            sc = next((s for s in scorecards if s["id"] == cid), None)
            assert sc is not None, f"No scorecard for candidate {cid}"
            assert sc["wer"] == pytest.approx(comp["metrics"]["wer"], abs=1e-4)
            assert sc["bleu"] == pytest.approx(comp["metrics"]["bleu"], abs=0.01)
            assert sc["chrf"] == pytest.approx(comp["metrics"]["chrf"], abs=0.01)

    def test_composite_formula(self):
        """composite = 0.5*(1-WER) + 0.25*(BLEU/100) + 0.25*(chrF/100)."""
        from core.benchmark.html_report import build_scorecards

        data = _load_fixture()
        scorecards = build_scorecards(data)

        for sc in scorecards:
            if sc["composite_score"] is None or sc["is_reference"]:
                continue
            expected = (0.5 * (1.0 - sc["wer"])
                        + 0.25 * (sc["bleu"] / 100.0)
                        + 0.25 * (sc["chrf"] / 100.0))
            assert sc["composite_score"] == pytest.approx(expected, abs=1e-4)

    def test_scorecards_empty_candidates(self):
        from core.benchmark.html_report import build_scorecards

        empty_results = {"video": "x.mkv", "reference_id": "", "candidates": [], "comparisons": []}
        scorecards = build_scorecards(empty_results)
        assert scorecards == []

    def test_scorecards_attached_to_run_benchmark_results(self, tmp_path, monkeypatch):
        """run_benchmark includes scorecards in the returned dict."""
        pytest.importorskip("jiwer")
        pytest.importorskip("sacrebleu")

        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, AudioStream, SubtitleStream

        synth = MediaInfo(
            path=Path("x.mkv"), format_name="matroska", duration=10.0,
            audio_streams=[AudioStream(index=0, codec="aac", language="en", raw_language="eng")],
            subtitle_streams=[SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng")],
        )
        segs = [Segment(start=0.0, end=1.0, text="hello")]

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth)
        monkeypatch.setattr(bm, "extract_subtitle_track",
                            lambda v, i, language, output_dir=None: SubtitleCandidate(
                                id=f"embedded_{language}_s{i}", language=language,
                                source="embedded", origin_stream=f"sub:{i}",
                                segments=segs, meta={}))
        monkeypatch.setattr(bm, "extract_audio_with_ffmpeg", lambda v, o, n: Path(o).write_bytes(b""))

        class _ASR:
            def __init__(self, _c): pass
            def transcribe_audio_to_segments(self, _p, language):
                return segs, None

        monkeypatch.setattr(bm, "FasterWhisperASR", _ASR)
        monkeypatch.setattr(bm, "build_candidate_from_segments",
                            lambda segs, cfg, candidate_id, language, origin_stream:
                            SubtitleCandidate(id=candidate_id, language=language,
                                             source="asr", origin_stream=origin_stream,
                                             segments=segs, meta={}))

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {"use_embedded_en": True, "use_embedded_jp": False,
                        "use_en_audio": True, "use_ja_audio": False},
        }

        dummy_video = tmp_path / "ep04.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False,
                                   output_dir=str(tmp_path))
        assert "scorecards" in results
        assert len(results["scorecards"]) == len(results["candidates"])


# ===========================================================================
# Child #4 — HTML benchmark report renderer
# ===========================================================================

class TestHtmlReport:
    """render_html_report generates a valid, self-contained HTML document."""

    def test_render_returns_html_string(self):
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        html = render_html_report(data)

        assert isinstance(html, str)
        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "</html>" in html

    def test_html_contains_video_name(self):
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        html = render_html_report(data)

        assert data["video"] in html

    def test_html_contains_reference_id(self):
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        html = render_html_report(data)

        assert data["reference_id"] in html

    def test_html_contains_all_candidate_ids(self):
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        html = render_html_report(data)

        for cand in data["candidates"]:
            assert cand["id"] in html, f"Candidate {cand['id']} missing from report"

    def test_html_contains_diff_text(self):
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        html = render_html_report(data)

        for comp in data["comparisons"]:
            for diff in comp["diffs"]:
                assert diff["ref"] in html or diff["cand"] in html

    def test_html_written_to_file(self, tmp_path):
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        out = tmp_path / "report.html"
        html = render_html_report(data, str(out))

        assert out.exists()
        assert out.read_text(encoding="utf-8") == html

    def test_html_creates_parent_dirs(self, tmp_path):
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        nested = tmp_path / "a" / "b" / "report.html"
        render_html_report(data, str(nested))
        assert nested.exists()

    def test_html_no_comparisons(self):
        from core.benchmark.html_report import render_html_report

        data = dict(_load_fixture(), comparisons=[])
        html = render_html_report(data)

        assert "No comparisons recorded" in html

    def test_html_escapes_special_characters(self):
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        # Inject a XSS payload into a diff
        evil = '<script>alert("xss")</script>'
        data["comparisons"][0]["diffs"][0]["ref"] = evil
        html = render_html_report(data)

        # The raw script tag must NOT appear unescaped
        assert evil not in html
        assert "&lt;script&gt;" in html

    def test_html_generated_at_override(self):
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        ts = "2099-01-01 00:00 UTC"
        html = render_html_report(data, generated_at=ts)
        assert ts in html

    def test_html_benchmark_report_written_by_run_benchmark(self, tmp_path, monkeypatch):
        """run_benchmark must write a benchmark_report.html alongside JSON."""
        pytest.importorskip("jiwer")
        pytest.importorskip("sacrebleu")

        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, AudioStream, SubtitleStream

        synth = MediaInfo(
            path=Path("x.mkv"), format_name="matroska", duration=10.0,
            audio_streams=[AudioStream(index=0, codec="aac", language="en", raw_language="eng")],
            subtitle_streams=[SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng")],
        )
        segs = [Segment(start=0.0, end=1.0, text="test")]

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth)
        monkeypatch.setattr(bm, "extract_subtitle_track",
                            lambda v, i, language, output_dir=None: SubtitleCandidate(
                                id=f"embedded_{language}_s{i}", language=language,
                                source="embedded", origin_stream=f"sub:{i}",
                                segments=segs, meta={}))
        monkeypatch.setattr(bm, "extract_audio_with_ffmpeg", lambda v, o, n: Path(o).write_bytes(b""))

        class _ASR:
            def __init__(self, _c): pass
            def transcribe_audio_to_segments(self, _p, language):
                return segs, None

        monkeypatch.setattr(bm, "FasterWhisperASR", _ASR)
        monkeypatch.setattr(bm, "build_candidate_from_segments",
                            lambda segs, cfg, candidate_id, language, origin_stream:
                            SubtitleCandidate(id=candidate_id, language=language,
                                             source="asr", origin_stream=origin_stream,
                                             segments=segs, meta={}))

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {"use_embedded_en": True, "use_embedded_jp": False,
                        "use_en_audio": True, "use_ja_audio": False},
        }

        dummy_video = tmp_path / "ep05.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        bm.run_benchmark(str(dummy_video), cfg, use_llm=False, output_dir=str(tmp_path))

        html_report = tmp_path / "benchmark_report.html"
        assert html_report.exists(), "benchmark_report.html should be written"
        content = html_report.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content


# ===========================================================================
# Child #5 — Regression test fixtures
# ===========================================================================

class TestRegressionFixtures:
    """Fixture file validates stable benchmark output structure."""

    def test_fixture_file_exists(self):
        assert _SMALL_FIXTURE.exists(), f"Fixture not found: {_SMALL_FIXTURE}"

    def test_fixture_is_valid_json(self):
        data = _load_fixture()
        assert isinstance(data, dict)

    def test_fixture_has_required_keys(self):
        data = _load_fixture()
        required = {"video", "reference_id", "run_id", "candidates", "comparisons", "scorecards"}
        assert required.issubset(data.keys()), (
            f"Missing keys: {required - data.keys()}"
        )

    def test_fixture_reference_id_in_candidates(self):
        data = _load_fixture()
        cand_ids = {c["id"] for c in data["candidates"]}
        assert data["reference_id"] in cand_ids

    def test_fixture_comparisons_ref_matches_reference_id(self):
        data = _load_fixture()
        for comp in data["comparisons"]:
            assert comp["ref_id"] == data["reference_id"], (
                f"Comparison ref_id {comp['ref_id']} != {data['reference_id']}"
            )

    def test_fixture_scorecards_count_matches_candidates(self):
        data = _load_fixture()
        assert len(data["scorecards"]) == len(data["candidates"])

    def test_fixture_one_scorecard_is_reference(self):
        data = _load_fixture()
        ref_scorecards = [sc for sc in data["scorecards"] if sc.get("is_reference")]
        assert len(ref_scorecards) == 1
        assert ref_scorecards[0]["id"] == data["reference_id"]

    def test_fixture_non_reference_scorecards_have_metrics(self):
        data = _load_fixture()
        for sc in data["scorecards"]:
            if sc.get("is_reference"):
                continue
            assert sc["wer"] is not None
            assert sc["bleu"] is not None
            assert sc["chrf"] is not None
            assert sc["composite_score"] is not None

    def test_fixture_round_trips_through_html_renderer(self):
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        html = render_html_report(data)

        assert "<!DOCTYPE html>" in html
        assert data["video"] in html
        assert data["reference_id"] in html

    def test_fixture_scorecards_rebuilt_deterministically(self):
        """build_scorecards(fixture) must produce the same ranks on every run."""
        from core.benchmark.html_report import build_scorecards

        data = _load_fixture()
        sc1 = build_scorecards(data)
        sc2 = build_scorecards(data)

        assert [s["id"] for s in sc1] == [s["id"] for s in sc2]
        assert [s["rank"] for s in sc1] == [s["rank"] for s in sc2]

    def test_fixture_metrics_in_expected_range(self):
        data = _load_fixture()
        for comp in data["comparisons"]:
            m = comp["metrics"]
            assert 0.0 <= m["wer"], "WER must be non-negative"
            assert 0.0 <= m["bleu"] <= 100.0, "BLEU must be 0-100"
            assert 0.0 <= m["chrf"] <= 100.0, "chrF must be 0-100"


# ===========================================================================
# Issue #123 — Benchmark staleness / self-comparison / comparisons=0 warnings
# ===========================================================================

class TestBenchmarkStalenessGuards:
    """Acceptance criteria for issue #123: stale artifacts, self-comparison, and warnings."""

    # ------------------------------------------------------------------
    # HTML report includes run_id
    # ------------------------------------------------------------------

    def test_html_report_includes_run_id(self):
        """render_html_report must surface the run_id in the HTML output."""
        from core.benchmark.html_report import render_html_report

        data = dict(_load_fixture())
        data["run_id"] = "test-run-uuid-001"
        html = render_html_report(data)

        assert "test-run-uuid-001" in html, "run_id must appear in the HTML report"

    def test_html_report_run_id_missing_renders_without_crash(self):
        """When run_id is absent, report renders without raising an exception."""
        from core.benchmark.html_report import render_html_report

        data = {k: v for k, v in _load_fixture().items() if k != "run_id"}
        html = render_html_report(data)

        assert "<!DOCTYPE html>" in html  # renders without error

    # ------------------------------------------------------------------
    # Warning when comparisons=0
    # ------------------------------------------------------------------

    def test_html_report_warns_on_zero_comparisons(self):
        """HTML report must include a visible warning banner when comparisons=0."""
        from core.benchmark.html_report import render_html_report

        data = dict(_load_fixture(), comparisons=[])
        html = render_html_report(data)

        assert '<div class="warning-banner">' in html, "A warning-banner element is required for 0 comparisons"
        assert "No comparisons" in html

    def test_html_report_warning_banner_absent_when_comparisons_exist(self):
        """No warning banner when comparisons are present."""
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        assert data["comparisons"], "fixture must have comparisons for this test"
        html = render_html_report(data)

        assert '<div class="warning-banner">' not in html

    def test_html_report_displays_warning_field_from_results(self):
        """Custom warning message from results dict is shown in the banner."""
        from core.benchmark.html_report import render_html_report

        data = dict(_load_fixture(), comparisons=[],
                    warning="Only one candidate was generated.")
        html = render_html_report(data)

        assert "Only one candidate was generated." in html

    def test_run_benchmark_adds_warning_field_for_single_candidate(
        self, tmp_path, monkeypatch
    ):
        """run_benchmark sets results['warning'] when only the reference candidate exists."""
        pytest.importorskip("jiwer")
        pytest.importorskip("sacrebleu")

        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, SubtitleStream

        # Only one EN subtitle stream -> single candidate -> no comparisons
        synth = MediaInfo(
            path=Path("x.mkv"), format_name="matroska", duration=10.0,
            audio_streams=[],
            subtitle_streams=[
                SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng"),
            ],
        )
        segs = [Segment(start=0.0, end=1.0, text="hello")]

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth)
        monkeypatch.setattr(bm, "extract_subtitle_track",
                            lambda v, i, language, output_dir=None: SubtitleCandidate(
                                id=f"embedded_{language}_s{i}", language=language,
                                source="embedded", origin_stream=f"sub:{i}",
                                segments=segs, meta={}))

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {"use_embedded_en": True, "use_embedded_jp": False,
                        "use_en_audio": False, "use_ja_audio": False},
        }

        dummy_video = tmp_path / "single.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False,
                                   output_dir=str(tmp_path))

        assert results["comparisons"] == [], "Should produce no comparisons"
        assert "warning" in results, "results must include a warning field"
        assert results["warning"], "warning field must not be empty"

    # ------------------------------------------------------------------
    # Self-comparison guard in _persist_comparison
    # ------------------------------------------------------------------

    def test_persist_comparison_skips_self_comparison(self, tmp_path, monkeypatch):
        """_persist_comparison must not record a run where ref_id == cand_id."""
        pytest.importorskip("jiwer")
        pytest.importorskip("sacrebleu")

        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, SubtitleStream
        from core.artifacts import ArtifactRegistry

        synth = MediaInfo(
            path=Path("x.mkv"), format_name="matroska", duration=10.0,
            audio_streams=[],
            subtitle_streams=[
                SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng"),
                SubtitleStream(index=1, codec="subrip", language="en", raw_language="eng"),
            ],
        )
        segs = [Segment(start=0.0, end=1.0, text="hello")]

        # Return identical IDs for both streams to trigger the self-comparison guard
        def _fake_extract(v, i, language, output_dir=None):
            return SubtitleCandidate(
                id="embedded_en_s0",  # always the same ID
                language=language, source="embedded",
                origin_stream=f"sub:{i}", segments=segs, meta={},
            )

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth)
        monkeypatch.setattr(bm, "extract_subtitle_track", _fake_extract)

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {"use_embedded_en": True, "use_embedded_jp": False,
                        "use_en_audio": False, "use_ja_audio": False},
        }

        dummy_video = tmp_path / "dup.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        registry = ArtifactRegistry(db_path=":memory:")
        results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False,
                                   output_dir=str(tmp_path), registry=registry)

        # No comparisons should be recorded when all candidate IDs equal the reference ID
        from core.artifacts.pipeline_wiring import compute_media_hash
        stored = registry.list_benchmark_runs(compute_media_hash(dummy_video))
        assert len(stored) == 0, (
            f"Self-comparison must not be persisted; found {len(stored)} records"
        )

    # ------------------------------------------------------------------
    # Segment count stored in registry matches comparison num_segments
    # ------------------------------------------------------------------

    def test_registry_record_includes_num_segments(self, tmp_path, monkeypatch):
        """Persisted BenchmarkRunRecord metrics include num_segments from comparison."""
        pytest.importorskip("jiwer")
        pytest.importorskip("sacrebleu")

        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, AudioStream, SubtitleStream
        from core.artifacts import ArtifactRegistry
        from core.artifacts.pipeline_wiring import compute_media_hash

        synth = MediaInfo(
            path=Path("x.mkv"), format_name="matroska", duration=10.0,
            audio_streams=[AudioStream(index=0, codec="aac", language="en", raw_language="eng")],
            subtitle_streams=[SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng")],
        )
        segs = [Segment(start=0.0, end=1.0, text="hello world")]

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth)
        monkeypatch.setattr(bm, "extract_subtitle_track",
                            lambda v, i, language, output_dir=None: SubtitleCandidate(
                                id=f"embedded_{language}_s{i}", language=language,
                                source="embedded", origin_stream=f"sub:{i}",
                                segments=segs, meta={}))
        monkeypatch.setattr(bm, "extract_audio_with_ffmpeg",
                            lambda v, o, n: Path(o).write_bytes(b""))

        class _ASR:
            def __init__(self, _c): pass
            def transcribe_audio_to_segments(self, _p, language):
                return segs, None

        monkeypatch.setattr(bm, "FasterWhisperASR", _ASR)
        monkeypatch.setattr(bm, "build_candidate_from_segments",
                            lambda s, c, candidate_id, language, origin_stream:
                            SubtitleCandidate(id=candidate_id, language=language,
                                             source="asr", origin_stream=origin_stream,
                                             segments=s, meta={}))

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {"use_embedded_en": True, "use_embedded_jp": False,
                        "use_en_audio": True, "use_ja_audio": False},
        }

        dummy_video = tmp_path / "segs.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        registry = ArtifactRegistry(db_path=":memory:")
        results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False,
                                   output_dir=str(tmp_path), registry=registry)

        assert results["comparisons"], "Need at least one comparison for this test"
        stored = registry.list_benchmark_runs(compute_media_hash(dummy_video))
        assert stored, "Registry should have at least one run"

        for record, comp in zip(stored, results["comparisons"]):
            assert "num_segments" in record.metrics, (
                "Persisted metrics must include num_segments"
            )
            assert record.metrics["num_segments"] == comp["num_segments"], (
                f"Registry num_segments {record.metrics['num_segments']} "
                f"!= comparison num_segments {comp['num_segments']}"
            )

    # ------------------------------------------------------------------
    # Atomic JSON write — stale artifacts
    # ------------------------------------------------------------------

    def test_json_output_no_tmp_file_after_success(self, tmp_path, monkeypatch):
        """benchmark_results.json.tmp must not remain after a successful write."""
        pytest.importorskip("jiwer")
        pytest.importorskip("sacrebleu")

        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, AudioStream, SubtitleStream

        synth = MediaInfo(
            path=Path("x.mkv"), format_name="matroska", duration=10.0,
            audio_streams=[AudioStream(index=0, codec="aac", language="en", raw_language="eng")],
            subtitle_streams=[SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng")],
        )
        segs = [Segment(start=0.0, end=1.0, text="atomic")]

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth)
        monkeypatch.setattr(bm, "extract_subtitle_track",
                            lambda v, i, language, output_dir=None: SubtitleCandidate(
                                id=f"embedded_{language}_s{i}", language=language,
                                source="embedded", origin_stream=f"sub:{i}",
                                segments=segs, meta={}))
        monkeypatch.setattr(bm, "extract_audio_with_ffmpeg",
                            lambda v, o, n: Path(o).write_bytes(b""))

        class _ASR:
            def __init__(self, _c): pass
            def transcribe_audio_to_segments(self, _p, language):
                return segs, None

        monkeypatch.setattr(bm, "FasterWhisperASR", _ASR)
        monkeypatch.setattr(bm, "build_candidate_from_segments",
                            lambda s, c, candidate_id, language, origin_stream:
                            SubtitleCandidate(id=candidate_id, language=language,
                                             source="asr", origin_stream=origin_stream,
                                             segments=s, meta={}))

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {"use_embedded_en": True, "use_embedded_jp": False,
                        "use_en_audio": True, "use_ja_audio": False},
        }

        dummy_video = tmp_path / "atomic.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        bm.run_benchmark(str(dummy_video), cfg, use_llm=False, output_dir=str(tmp_path))

        assert (tmp_path / "benchmark_results.json").exists(), "JSON output must exist"
        assert not (tmp_path / "benchmark_results.json.tmp").exists(), (
            ".tmp file must not remain after a successful write"
        )


# ===========================================================================
# Single-candidate detection
# ===========================================================================

class TestSingleCandidateDetection:
    """run_benchmark with only one candidate reports status=single_candidate_only."""

    def _make_single_candidate_results(self, tmp_path, monkeypatch):
        """Run run_benchmark with only one EN candidate available."""
        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, SubtitleStream

        synth = MediaInfo(
            path=Path("x.mkv"),
            format_name="matroska",
            duration=10.0,
            audio_streams=[],
            subtitle_streams=[
                SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng")
            ],
        )
        segs = [Segment(start=0.0, end=1.0, text="hello")]

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth)
        monkeypatch.setattr(
            bm,
            "extract_subtitle_track",
            lambda v, i, language, output_dir=None: SubtitleCandidate(
                id=f"embedded_{language}_s{i}",
                language=language,
                source="embedded",
                origin_stream=f"sub:{i}",
                segments=segs,
                meta={},
            ),
        )

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {
                "use_embedded_en": True,
                "use_embedded_jp": False,
                "use_en_audio": False,
                "use_ja_audio": False,
            },
        }

        dummy_video = tmp_path / "ep01.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        return bm.run_benchmark(str(dummy_video), cfg, use_llm=False, output_dir=str(tmp_path))

    def test_status_is_single_candidate_only(self, tmp_path, monkeypatch):
        results = self._make_single_candidate_results(tmp_path, monkeypatch)
        assert results["status"] == "single_candidate_only"

    def test_warning_field_present(self, tmp_path, monkeypatch):
        results = self._make_single_candidate_results(tmp_path, monkeypatch)
        assert "warning" in results
        assert results["warning"]

    def test_comparisons_empty(self, tmp_path, monkeypatch):
        results = self._make_single_candidate_results(tmp_path, monkeypatch)
        assert results["comparisons"] == []

    def test_json_output_contains_warning(self, tmp_path, monkeypatch):
        self._make_single_candidate_results(tmp_path, monkeypatch)
        out = tmp_path / "benchmark_results.json"
        assert out.exists(), "benchmark_results.json should be written"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data.get("status") == "single_candidate_only"
        assert data.get("warning")

    def test_html_report_says_no_comparison_possible(self, tmp_path, monkeypatch):
        self._make_single_candidate_results(tmp_path, monkeypatch)
        html = (tmp_path / "benchmark_report.html").read_text(encoding="utf-8")
        assert "No benchmark comparison possible" in html

    def test_html_report_shows_warning_banner(self, tmp_path, monkeypatch):
        self._make_single_candidate_results(tmp_path, monkeypatch)
        html = (tmp_path / "benchmark_report.html").read_text(encoding="utf-8")
        assert '<div class="warning-banner">' in html

    def test_render_html_report_single_candidate_status(self):
        """render_html_report shows the single-candidate no-comparison message."""
        from core.benchmark.html_report import render_html_report

        data = {
            "video": "test.mkv",
            "reference_id": "embedded_en_s0",
            "run_id": "test-run",
            "status": "single_candidate_only",
            "warning": "Only one candidate - no comparison possible.",
            "candidates": [
                {
                    "id": "embedded_en_s0",
                    "source": "embedded",
                    "language": "en",
                    "origin_stream": "sub:0",
                    "segment_count": 1,
                }
            ],
            "comparisons": [],
        }
        html = render_html_report(data)
        assert "No benchmark comparison possible" in html
        assert '<div class="warning-banner">' in html

    def test_render_html_report_ok_status_no_banner(self):
        """Normal results must not show the warning banner element."""
        from core.benchmark.html_report import render_html_report

        data = _load_fixture()
        html = render_html_report(data)
        assert '<div class="warning-banner">' not in html

    def test_multi_candidate_status_is_ok(self, tmp_path, monkeypatch):
        """When multiple candidates exist, status must be ok."""
        pytest.importorskip("jiwer")
        pytest.importorskip("sacrebleu")

        import benchmark as bm
        from config import Config
        from models import Segment, SubtitleCandidate
        from media_inspect import MediaInfo, AudioStream, SubtitleStream

        synth = MediaInfo(
            path=Path("x.mkv"),
            format_name="matroska",
            duration=10.0,
            audio_streams=[AudioStream(index=0, codec="aac", language="en", raw_language="eng")],
            subtitle_streams=[
                SubtitleStream(index=0, codec="subrip", language="en", raw_language="eng")
            ],
        )
        segs = [Segment(start=0.0, end=1.0, text="hello")]

        monkeypatch.setattr(bm, "inspect_media", lambda _: synth)
        monkeypatch.setattr(
            bm,
            "extract_subtitle_track",
            lambda v, i, language, output_dir=None: SubtitleCandidate(
                id=f"embedded_{language}_s{i}",
                language=language,
                source="embedded",
                origin_stream=f"sub:{i}",
                segments=segs,
                meta={},
            ),
        )
        monkeypatch.setattr(
            bm, "extract_audio_with_ffmpeg", lambda v, o, n: Path(o).write_bytes(b"")
        )

        class _ASR:
            def __init__(self, _c): pass
            def transcribe_audio_to_segments(self, _p, language):
                return segs, None

        monkeypatch.setattr(bm, "FasterWhisperASR", _ASR)
        monkeypatch.setattr(
            bm,
            "build_candidate_from_segments",
            lambda s, c, candidate_id, language, origin_stream: SubtitleCandidate(
                id=candidate_id,
                language=language,
                source="asr",
                origin_stream=origin_stream,
                segments=s,
                meta={},
            ),
        )

        cfg = Config()
        cfg._config["benchmark"] = {
            "sources": {
                "use_embedded_en": True,
                "use_embedded_jp": False,
                "use_en_audio": True,
                "use_ja_audio": False,
            },
        }

        dummy_video = tmp_path / "ep02.mkv"
        dummy_video.write_bytes(b"\x00" * 16)

        results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False, output_dir=str(tmp_path))
        assert results["status"] == "ok"
        assert "warning" not in results
