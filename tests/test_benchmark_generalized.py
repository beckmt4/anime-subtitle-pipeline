"""Tests for generalized benchmark orchestration (multi-track, multi-source).

These tests monkeypatch heavy I/O and external processing routines so that
`run_benchmark` can be executed deterministically without requiring ffmpeg,
whisper models, or actual media files.
"""

import os
from pathlib import Path
from typing import List

import pytest

# Skip the entire module if optional metric libraries are not installed
pytest.importorskip("jiwer")
pytest.importorskip("sacrebleu")

from config import Config
from core.ocr import OCRBackend
from models import Segment, SubtitleCandidate
from media_inspect import MediaInfo, AudioStream, SubtitleStream
import benchmark as bm


# ---------------------------------------------------------------------------
# Helper stubs
# ---------------------------------------------------------------------------

def _make_segments(prefix: str) -> List[Segment]:
    return [
        Segment(start=0.0, end=1.5, text=f"{prefix} line one"),
        Segment(start=1.6, end=3.0, text=f"{prefix} line two"),
    ]


class DummyASR:
    def __init__(self, _config):
        pass

    def transcribe_audio_to_segments(self, _path: str, language: str):
        segs = _make_segments(f"asr_{language}")
        cand = SubtitleCandidate(
            id=f"asr_{language}",
            language=language,
            source="asr",
            origin_stream="audio:0",
            segments=segs,
            meta={"dummy": True},
        )
        return segs, cand


def dummy_build_candidate_from_segments(segments, config, candidate_id, language, origin_stream):
    return SubtitleCandidate(
        id=candidate_id,
        language=language,
        source="asr" if language == "en" else "asr_mt",
        origin_stream=origin_stream,
        segments=segments,
        meta={"dummy": True},
    )


class DummyOCRBackend(OCRBackend):
    def extract(self, video_path: str, stream_index: int, language_hint: str | None = None):
        lang = language_hint or "und"
        return SubtitleCandidate(
            id=f"bitmap_{lang}_s{stream_index}",
            language=lang,
            source="embedded",
            origin_stream=f"sub:{stream_index}",
            segments=[
                Segment(start=0.0, end=1.5, text=f"bitmap-{lang}-1", meta={"ocr_confidence": 0.9}),
                Segment(start=1.6, end=3.0, text=f"bitmap-{lang}-2", meta={"ocr_confidence": 0.92}),
            ],
            meta={},
        )


def _subtitle_stream(global_index: int) -> SubtitleStream | None:
    for stream in _SYNTH_MEDIA.subtitle_streams:
        if stream.index == global_index:
            return stream
    return None


def dummy_extract_subtitle_track(video, sub_index, language, output_dir=None, ocr_backend=None):
    stream = _subtitle_stream(sub_index)
    if stream is not None and stream.is_bitmap:
        if ocr_backend is None:
            raise RuntimeError("OCR backend not configured")
        return ocr_backend.extract(str(video), sub_index, language_hint=language)

    return SubtitleCandidate(
        id=f"embedded_{language}_s{sub_index}",
        language=language,
        source="embedded",
        origin_stream=f"sub:{sub_index}",
        segments=_make_segments(f"emb_{language}"),
        meta={"global_index": sub_index},
    )


def dummy_translate_candidate_jp_to_en(cand: SubtitleCandidate, config: Config, engine=None):
    # Produce a shallow copy with language changed and id updated
    engine = engine or config.get("translation", "engine", default="marian")
    return SubtitleCandidate(
        id=cand.id.replace("embedded_ja", "embedded_jp_mt").replace("_ja_", "_en_") + f"_{engine}",
        language="en",
        source="embedded_mt" if cand.source == "embedded" else "asr_mt",
        origin_stream=cand.origin_stream,
        segments=[Segment(start=s.start, end=s.end, text=s.text + " (mt)") for s in cand.segments],
        meta={
            **cand.meta.copy(),
            "translation_engine": engine,
            "translation_model": f"model-{engine}",
            "translation_mode": "accuracy_first",
            "translation_fallback": False,
        },
    )


def dummy_translate_candidate_jp_to_en_workflow(
    cand: SubtitleCandidate,
    config: Config,
    engine=None,
    ja_candidate=None,
):
    translated = dummy_translate_candidate_jp_to_en(cand, config, engine=engine)
    workflow = config.get("translation", "workflow", default="single_pass")
    translated.meta["translation_workflow"] = workflow
    if workflow == "literal_then_natural":
        translated.id = f"{translated.id}_natural"
        translated.source = "two_pass_llm"
    return translated


def dummy_polish_candidate_with_llm(cand: SubtitleCandidate, config: Config):
    return SubtitleCandidate(
        id=cand.id + "_llm",
        language=cand.language,
        source=cand.source + "_llm",
        origin_stream=cand.origin_stream,
        segments=[Segment(start=s.start, end=s.end, text=s.text.replace("line", "ln")) for s in cand.segments],
        meta=cand.meta,
    )


def dummy_enforce_constraints_on_candidate(cand: SubtitleCandidate, config: Config):
    return cand  # No-op for tests


def dummy_extract_audio_with_ffmpeg(video_path: str, out_path: str, audio_order: int):
    # No-op (would normally create wav file)
    Path(out_path).write_bytes(b"")


# ---------------------------------------------------------------------------
# Monkeypatch installation
# ---------------------------------------------------------------------------

def _install_monkeypatches():
    bm.inspect_media = lambda path: _SYNTH_MEDIA
    bm.extract_subtitle_track = dummy_extract_subtitle_track
    bm.translate_candidate_jp_to_en_workflow = dummy_translate_candidate_jp_to_en_workflow
    bm.polish_candidate_with_llm = dummy_polish_candidate_with_llm
    bm.enforce_constraints_on_candidate = dummy_enforce_constraints_on_candidate
    bm.extract_audio_with_ffmpeg = dummy_extract_audio_with_ffmpeg
    bm.FasterWhisperASR = DummyASR
    bm.build_candidate_from_segments = dummy_build_candidate_from_segments


# ---------------------------------------------------------------------------
# Synthetic media description used across tests
# ---------------------------------------------------------------------------

_SYNTH_MEDIA = MediaInfo(
    path=Path("dummy.mkv"),
    format_name="matroska",
    duration=120.0,
    audio_streams=[
        AudioStream(index=0, codec="aac", language="en", raw_language="eng"),
        AudioStream(index=1, codec="aac", language="en", raw_language="eng"),
        AudioStream(index=2, codec="aac", language="ja", raw_language="jpn"),
    ],
    subtitle_streams=[
        SubtitleStream(index=10, codec="subrip", language="en", raw_language="eng"),
        SubtitleStream(index=11, codec="subrip", language="ja", raw_language="jpn"),
    ],
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_generalized_generation_and_reference():
    """End-to-end run with all sources enabled, verifying counts and reference selection."""
    _install_monkeypatches()
    cfg = Config()
    # Enable pairwise comparisons for second part of test
    cfg._config.setdefault("benchmark", {})
    cfg._config["benchmark"].update({
        "sources": {
            "use_embedded_en": True,
            "use_embedded_jp": True,
            "use_en_audio": True,
            "use_ja_audio": True,
        },
        "reference_priority": [
            "embedded_en",
            "en_audio_asr",
            "ja_audio_asr_mt",
            "embedded_jp_mt",
        ],
        "compare_all_pairs": False,
    })

    # Create a dummy file to satisfy existence check
    dummy_video = Path("temp/test_video.mkv")
    dummy_video.parent.mkdir(parents=True, exist_ok=True)
    dummy_video.write_bytes(b"00")

    results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False)

    # Expected candidate counts:
    # 1 embedded EN + 1 embedded JP->MT + 2 EN audio ASR + 1 JP audio ASR->MT = 5
    assert len(results["candidates"]) == 5, f"Unexpected candidate count: {len(results['candidates'])}" 
    assert results["reference_id"].startswith("embedded_en"), "Embedded EN should be reference"
    assert "review_task_routing" in results
    assert "status" in results["review_task_routing"]
    # Reference comparisons only (N-1)
    assert len([c for c in results["comparisons"] if c["ref_id"] == results["reference_id"]]) == 4

    # Enable full pairwise matrix
    cfg._config["benchmark"]["compare_all_pairs"] = True
    results_full = bm.run_benchmark(str(dummy_video), cfg, use_llm=False)
    # Total comparisons = (N-1 reference) + N*(N-1)/2 pairwise
    n = 5
    expected = (n - 1) + (n * (n - 1) // 2)
    assert len(results_full["comparisons"]) == expected, (
        f"Expected {expected} comparisons with pairwise enabled, got {len(results_full['comparisons'])}" 
    )

    print("✓ Generalized generation & reference selection test passed")


def test_reference_selection_without_embedded_en():
    """Verify fallback reference when embedded EN subtitle is absent."""
    _install_monkeypatches()
    cfg = Config()
    # Remove embedded EN stream from synthetic media
    _SYNTH_MEDIA.subtitle_streams = [s for s in _SYNTH_MEDIA.subtitle_streams if s.language != "en"]
    cfg._config.setdefault("benchmark", {})
    cfg._config["benchmark"].update({
        "sources": {
            "use_embedded_en": True,  # Enabled but absent
            "use_embedded_jp": True,
            "use_en_audio": True,
            "use_ja_audio": True,
        },
        "reference_priority": [
            "embedded_en",
            "en_audio_asr",
            "ja_audio_asr_mt",
            "embedded_jp_mt",
        ],
        "compare_all_pairs": False,
    })

    dummy_video = Path("temp/test_video_no_en.mkv")
    dummy_video.parent.mkdir(parents=True, exist_ok=True)
    dummy_video.write_bytes(b"00")

    results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False)

    # Since no embedded EN, reference should fall back to first en_audio_asr candidate
    assert results["reference_id"].startswith("en_audio_asr"), (
        f"Expected en_audio_asr fallback reference, got {results['reference_id']}" 
    )
    print("✓ Reference fallback test passed")

    # Restore synthetic media for other tests
    _SYNTH_MEDIA.subtitle_streams.append(
        SubtitleStream(index=10, codec="subrip", language="en", raw_language="eng")
    )


def test_benchmark_can_compare_translation_engines():
    """Benchmark mode should emit separate JP-source candidates per configured engine."""
    _install_monkeypatches()
    cfg = Config()
    cfg._config.setdefault("benchmark", {})
    cfg._config["benchmark"].update({
        "sources": {
            "use_embedded_en": True,
            "use_embedded_jp": True,
            "use_en_audio": False,
            "use_ja_audio": True,
        },
        "translation_engines": ["marian", "llm_direct"],
        "reference_priority": ["embedded_en", "embedded_jp_mt", "ja_audio_asr_mt"],
        "compare_all_pairs": False,
    })

    dummy_video = Path("temp/test_video_translation_engines.mkv")
    dummy_video.parent.mkdir(parents=True, exist_ok=True)
    dummy_video.write_bytes(b"00")

    results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False)

    engine_candidates = [
        c for c in results["candidates"]
        if c.get("translation_engine") in {"marian", "llm_direct"}
    ]
    assert len(engine_candidates) == 4, engine_candidates
    assert {c["translation_engine"] for c in engine_candidates} == {"marian", "llm_direct"}
    assert all("translation_qc" in c for c in engine_candidates)
    assert all(c["translation_qc"].get("qc_status") in {"pass", "warn", "fail"} for c in engine_candidates)
    assert all("summary" in c["translation_qc"] for c in engine_candidates)
    assert all(c.get("translation_workflow") == "single_pass" for c in engine_candidates)


def test_benchmark_records_workflow_metadata_for_jp_candidates():
    """JP-derived benchmark candidates should include translation_workflow metadata."""
    _install_monkeypatches()
    cfg = Config()
    cfg._config.setdefault("translation", {})
    cfg._config["translation"]["workflow"] = "single_pass"
    cfg._config.setdefault("benchmark", {})
    cfg._config["benchmark"].update({
        "sources": {
            "use_embedded_en": True,
            "use_embedded_jp": True,
            "use_en_audio": False,
            "use_ja_audio": True,
        },
        "translation_engines": ["marian"],
        "reference_priority": ["embedded_en", "embedded_jp_mt", "ja_audio_asr_mt"],
        "compare_all_pairs": False,
    })

    dummy_video = Path("temp/test_video_workflow_metadata.mkv")
    dummy_video.parent.mkdir(parents=True, exist_ok=True)
    dummy_video.write_bytes(b"00")

    results = bm.run_benchmark(str(dummy_video), cfg, use_llm=False)

    jp_candidates = [c for c in results["candidates"] if c["source"].startswith(("embedded_mt_", "asr_mt_"))]
    assert jp_candidates, "Expected JP-derived candidates in benchmark results"
    assert all(c.get("translation_workflow") == "single_pass" for c in jp_candidates), jp_candidates


def test_benchmark_two_pass_skips_generic_llm_polish_by_default():
    """literal_then_natural should not be followed by generic benchmark LLM polish unless opted in."""
    _install_monkeypatches()
    cfg = Config()
    cfg._config.setdefault("translation", {})
    cfg._config["translation"]["workflow"] = "literal_then_natural"
    cfg._config.setdefault("benchmark", {})
    cfg._config["benchmark"].update({
        "sources": {
            "use_embedded_en": True,
            "use_embedded_jp": True,
            "use_en_audio": False,
            "use_ja_audio": True,
        },
        "translation_engines": ["marian"],
        "reference_priority": ["embedded_en", "embedded_jp_mt", "ja_audio_asr_mt"],
        "compare_all_pairs": False,
    })

    dummy_video = Path("temp/test_video_two_pass_workflow.mkv")
    dummy_video.parent.mkdir(parents=True, exist_ok=True)
    dummy_video.write_bytes(b"00")

    results = bm.run_benchmark(str(dummy_video), cfg, use_llm=True)

    jp_candidates = [c for c in results["candidates"] if c["source"].startswith(("embedded_mt_", "asr_mt_"))]
    assert jp_candidates, "Expected JP-derived candidates in benchmark results"
    assert all(c.get("translation_workflow") == "literal_then_natural" for c in jp_candidates), jp_candidates
    assert all(not c["source"].endswith("_llm") for c in jp_candidates), jp_candidates


def test_benchmark_includes_bitmap_candidates_when_ocr_enabled():
    _install_monkeypatches()
    cfg = Config()
    cfg._config.setdefault("benchmark", {})
    cfg._config["benchmark"].update({
        "sources": {
            "use_embedded_en": True,
            "use_embedded_jp": True,
            "use_en_audio": False,
            "use_ja_audio": False,
        },
        "translation_engines": ["marian"],
        "reference_priority": ["bitmap_en", "embedded_en"],
        "compare_all_pairs": False,
    })

    original_subs = list(_SYNTH_MEDIA.subtitle_streams)
    _SYNTH_MEDIA.subtitle_streams = original_subs + [
        SubtitleStream(index=12, codec="pgssub", language="en", raw_language="eng", is_bitmap=True),
        SubtitleStream(index=13, codec="pgssub", language="ja", raw_language="jpn", is_bitmap=True),
    ]
    try:
        dummy_video = Path("temp/test_video_bitmap_ocr.mkv")
        dummy_video.parent.mkdir(parents=True, exist_ok=True)
        dummy_video.write_bytes(b"00")

        results = bm.run_benchmark(
            str(dummy_video), cfg, use_llm=False, ocr_backend=DummyOCRBackend()
        )
    finally:
        _SYNTH_MEDIA.subtitle_streams = original_subs

    candidate_ids = {c["id"] for c in results["candidates"]}
    candidate_sources = {c["source"] for c in results["candidates"]}

    assert "bitmap_en_s12" in candidate_ids
    assert any(source.startswith("bitmap_mt_") for source in candidate_sources)


def test_benchmark_bitmap_only_requires_ocr_backend():
    _install_monkeypatches()
    cfg = Config()
    cfg._config.setdefault("benchmark", {})
    cfg._config["benchmark"].update({
        "sources": {
            "use_embedded_en": True,
            "use_embedded_jp": True,
            "use_en_audio": False,
            "use_ja_audio": False,
        },
        "translation_engines": ["marian"],
        "compare_all_pairs": False,
    })

    original_audio = list(_SYNTH_MEDIA.audio_streams)
    original_subs = list(_SYNTH_MEDIA.subtitle_streams)
    _SYNTH_MEDIA.audio_streams = []
    _SYNTH_MEDIA.subtitle_streams = [
        SubtitleStream(index=22, codec="pgssub", language="en", raw_language="eng", is_bitmap=True),
        SubtitleStream(index=23, codec="pgssub", language="ja", raw_language="jpn", is_bitmap=True),
    ]
    try:
        dummy_video = Path("temp/test_video_bitmap_only.mkv")
        dummy_video.parent.mkdir(parents=True, exist_ok=True)
        dummy_video.write_bytes(b"00")

        with pytest.raises(RuntimeError, match="OCR backend is not configured"):
            bm.run_benchmark(str(dummy_video), cfg, use_llm=False, ocr_backend=None)
    finally:
        _SYNTH_MEDIA.audio_streams = original_audio
        _SYNTH_MEDIA.subtitle_streams = original_subs


def run_all_generalized_tests():
    print("Running generalized benchmark tests...\n")
    test_generalized_generation_and_reference()
    test_reference_selection_without_embedded_en()
    print("\n✅ All generalized benchmark tests PASSED")


if __name__ == "__main__":
    os.environ.setdefault("TRACING_ENABLED", "false")
    run_all_generalized_tests()
