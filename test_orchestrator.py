"""Tests for generation strategy selection in orchestrator.run_generate.

Uses monkeypatching to avoid heavy I/O / model calls. Focuses purely on
decision logic given different MediaInfo configurations.
"""
from pathlib import Path
from typing import List

from models import SubtitleCandidate, Segment
from media_inspect import MediaInfo, AudioStream, SubtitleStream
from config import Config
import orchestrator as orch

# ---------------------------------------------------------------------------
# Helper candidate factories (lightweight)
# ---------------------------------------------------------------------------

def make_segments(tag: str) -> List[Segment]:
    return [Segment(start=0.0, end=1.0, text=f"{tag} one"), Segment(start=1.1, end=2.0, text=f"{tag} two")]


def stub_extract_subtitle_track(video, sub_index, language, output_dir=None):
    return SubtitleCandidate(
        id=f"embedded_{language}_s{sub_index}",
        language=language,
        source="embedded",
        origin_stream=f"sub:{sub_index}",
        segments=make_segments(f"sub-{language}"),
        meta={},
    )


def stub_extract_audio_with_ffmpeg(video_path: str, out_path: str, audio_order: int):
    Path(out_path).write_bytes(b"")  # create dummy file
    return out_path


class DummyASR:
    def __init__(self, cfg):
        pass

    def transcribe_audio_to_segments(self, path: str, language: str = "en"):
        return make_segments(f"asr-{language}")


def stub_build_candidate_from_segments(segments, cfg, candidate_id, language, origin_stream):
    return SubtitleCandidate(
        id=candidate_id,
        language=language,
        source="asr" if language == "en" else "asr_mt",
        origin_stream=origin_stream,
        segments=segments,
        meta={},
    )


def stub_translate_candidate_jp_to_en(cand: SubtitleCandidate, cfg: Config):
    return SubtitleCandidate(
        id=cand.id.replace("embedded_ja", "embedded_jp_mt").replace("ja_audio_asr", "ja_audio_asr_mt"),
        language="en",
        source="embedded_mt" if cand.source == "embedded" else "asr_mt",
        origin_stream=cand.origin_stream,
        segments=[Segment(start=s.start, end=s.end, text=s.text + " EN") for s in cand.segments],
        meta={},
    )


def stub_polish_candidate_with_llm(cand: SubtitleCandidate, cfg: Config):
    return SubtitleCandidate(
        id=cand.id + "_llm",
        language="en",
        source=cand.source + "_llm",
        origin_stream=cand.origin_stream,
        segments=[Segment(start=s.start, end=s.end, text=s.text.replace("one", "1")) for s in cand.segments],
        meta=cand.meta,
    )


def stub_polish_candidate_no_change(cand: SubtitleCandidate, cfg: Config):
    """Polish stub that returns identical text — simulates a no-op LLM."""
    return SubtitleCandidate(
        id=cand.id + "_llm",
        language="en",
        source=cand.source + "_llm",
        origin_stream=cand.origin_stream,
        segments=[Segment(start=s.start, end=s.end, text=s.text) for s in cand.segments],
        meta=cand.meta,
    )


def stub_polish_candidate_fallback(cand: SubtitleCandidate, cfg: Config):
    """Polish stub that simulates LLM unreachable (fallback pass-through)."""
    return SubtitleCandidate(
        id=cand.id + "_llm",
        language="en",
        source=cand.source + "_llm",
        origin_stream=cand.origin_stream,
        segments=[Segment(start=s.start, end=s.end, text=s.text) for s in cand.segments],
        meta={"fallback": True},
    )


def stub_enforce_constraints_on_candidate(cand: SubtitleCandidate, cfg: Config):
    return cand


def stub_write_candidate_srt(candidate: SubtitleCandidate, output_path: str, cfg: Config):
    p = Path(output_path)
    p.write_text("DUMMY SRT")
    return p


# Install monkeypatches once
orch.extract_subtitle_track = stub_extract_subtitle_track
orch.extract_audio_with_ffmpeg = stub_extract_audio_with_ffmpeg
orch.FasterWhisperASR = DummyASR
orch.build_candidate_from_segments = stub_build_candidate_from_segments
orch.translate_candidate_jp_to_en = stub_translate_candidate_jp_to_en
orch.polish_candidate_with_llm = stub_polish_candidate_with_llm
orch.enforce_constraints_on_candidate = stub_enforce_constraints_on_candidate
orch.write_candidate_srt = stub_write_candidate_srt

# Ensure temp/outbox dirs exist
Path("temp").mkdir(exist_ok=True)
Path("outbox").mkdir(exist_ok=True)


def _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=False,
           en_sub_lang="en") -> MediaInfo:
    """Build a minimal MediaInfo for strategy tests.

    en_sub_lang: the language tag stored on the English subtitle stream (allows
    testing non-trivial tags like 'eng', 'en-US', etc.).
    """
    subs = []
    auds = []
    idx = 0
    if en_audio:
        auds.append(AudioStream(index=idx, codec="aac", language="en")); idx += 1
    if jp_audio:
        auds.append(AudioStream(index=idx, codec="aac", language="ja")); idx += 1
    sidx = 10
    if en_sub:
        subs.append(SubtitleStream(index=sidx, codec="subrip",
                                   language=en_sub_lang,
                                   raw_language=en_sub_lang)); sidx += 1
    if jp_sub:
        subs.append(SubtitleStream(index=sidx, codec="subrip", language="ja")); sidx += 1
    return MediaInfo(path=Path("dummy.mkv"), format_name="matroska", duration=120.0,
                     audio_streams=auds, subtitle_streams=subs)


def test_strategy_embedded_en():
    cfg = Config()
    media = _media(en_sub=True, en_audio=True, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_en", meta
    print("✓ embedded_en strategy chosen correctly")


def test_strategy_en_audio_when_no_en_sub_and_en_audio_preferred():
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_subtitles"] = False
    cfg._config["generate"]["prefer_audio_language"] = "en"
    media = _media(en_sub=False, en_audio=True, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "en_audio_asr", meta
    print("✓ en_audio_asr strategy chosen correctly")


def test_strategy_embedded_jp_mt():
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_jp_mt", meta
    print("✓ embedded_jp_mt strategy chosen correctly")


def test_strategy_ja_audio_asr_mt():
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "ja_audio_asr_mt", meta
    print("✓ ja_audio_asr_mt strategy chosen correctly")


def test_strategy_en_audio_fallback():
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_subtitles"] = False
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "en_audio_asr", meta
    print("✓ en_audio_asr fallback strategy chosen correctly")


# --- Regression: real-world language tag variants ---

def test_embedded_en_selected_with_eng_tag():
    """Regression (A Couple of Cuckoos): 'eng' ISO-639-2 tagged EN sub must win over generation."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=False, jp_audio=True,
                   en_sub_lang="eng")
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_en", (
        f"Expected embedded_en but got {meta['strategy']} — "
        "'eng' tag was not recognised as English"
    )
    print("✓ embedded_en selected for 'eng'-tagged subtitle (A Couple of Cuckoos regression)")


def test_embedded_en_selected_with_bcp47_en_us_tag():
    """Regression (Once Upon a Crime): 'en-US' BCP-47 tagged EN sub must win over generation."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=True, jp_audio=True,
                   en_sub_lang="en-US")
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_en", (
        f"Expected embedded_en but got {meta['strategy']} — "
        "'en-US' BCP-47 tag was not recognised as English"
    )
    print("✓ embedded_en selected for 'en-US'-tagged subtitle (Once Upon a Crime regression)")


def test_skip_embedded_en_forces_generation():
    """Preserve skip_embedded_en behavior: when set, pipeline must not use embedded EN."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=False, jp_audio=True)
    meta = orch.run_generate(media, cfg, skip_embedded_en=True)
    assert meta["strategy"] != "embedded_en", (
        f"Expected generation strategy but got {meta['strategy']} — "
        "skip_embedded_en=True should bypass embedded EN subtitles"
    )
    print("✓ skip_embedded_en=True correctly bypasses embedded EN subtitles")


def run_all_tests():
    test_strategy_embedded_en()
    test_strategy_en_audio_when_no_en_sub_and_en_audio_preferred()
    test_strategy_embedded_jp_mt()
    test_strategy_ja_audio_asr_mt()
    test_strategy_en_audio_fallback()
    test_embedded_en_selected_with_eng_tag()
    test_embedded_en_selected_with_bcp47_en_us_tag()
    test_skip_embedded_en_forces_generation()
    test_compare_candidates_changed()
    test_compare_candidates_no_change()
    test_compare_candidates_fallback()
    test_polish_status_changed_in_metadata()
    test_polish_status_no_change_in_metadata()
    test_polish_status_fallback_in_metadata()
    test_no_polish_status_for_non_mt_strategies()
    print("\n✅ All orchestrator strategy tests PASSED")


# ---------------------------------------------------------------------------
# _compare_candidates unit tests
# ---------------------------------------------------------------------------

def test_compare_candidates_changed():
    raw = SubtitleCandidate(
        id="raw", language="en", source="mt", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello world"), Segment(1.0, 2.0, "Goodbye")],
        meta={},
    )
    polished = SubtitleCandidate(
        id="raw_llm", language="en", source="mt_llm", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello, world!"), Segment(1.0, 2.0, "Goodbye")],
        meta={},
    )
    result = orch._compare_candidates(raw, polished)
    assert result["polish_status"] == "changed", result
    assert result["segments_changed"] == 1
    assert result["segments_unchanged"] == 1
    print("✓ _compare_candidates: changed status correct")


def test_compare_candidates_no_change():
    raw = SubtitleCandidate(
        id="raw", language="en", source="mt", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello world"), Segment(1.0, 2.0, "Goodbye")],
        meta={},
    )
    polished = SubtitleCandidate(
        id="raw_llm", language="en", source="mt_llm", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello world"), Segment(1.0, 2.0, "Goodbye")],
        meta={},
    )
    result = orch._compare_candidates(raw, polished)
    assert result["polish_status"] == "no_change", result
    assert result["segments_changed"] == 0
    assert result["segments_unchanged"] == 2
    print("✓ _compare_candidates: no_change status correct")


def test_compare_candidates_fallback():
    raw = SubtitleCandidate(
        id="raw", language="en", source="mt", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello world"), Segment(1.0, 2.0, "Goodbye")],
        meta={},
    )
    polished = SubtitleCandidate(
        id="raw_llm", language="en", source="mt_llm", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello world"), Segment(1.0, 2.0, "Goodbye")],
        meta={"fallback": True},
    )
    result = orch._compare_candidates(raw, polished)
    assert result["polish_status"] == "fallback", result
    assert result["segments_changed"] == 0
    assert result["segments_unchanged"] == 2
    print("✓ _compare_candidates: fallback status correct")


# ---------------------------------------------------------------------------
# run_generate polish_status metadata tests
# ---------------------------------------------------------------------------

def test_polish_status_changed_in_metadata():
    """When LLM polish changes segments, metadata should report polish_status=changed."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=False)
    # Default stub (stub_polish_candidate_with_llm) changes text containing "one"
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_jp_mt"
    assert "polish_status" in meta, meta
    assert meta["polish_status"] == "changed", meta
    assert "segments_changed" in meta
    assert "segments_unchanged" in meta
    print("✓ polish_status=changed present in metadata for changed polish")


def test_polish_status_no_change_in_metadata():
    """When LLM polish leaves all segments identical, metadata reports no_change."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=False)
    original_stub = orch.polish_candidate_with_llm
    orch.polish_candidate_with_llm = stub_polish_candidate_no_change
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        orch.polish_candidate_with_llm = original_stub
    assert meta["strategy"] == "embedded_jp_mt"
    assert meta["polish_status"] == "no_change", meta
    assert meta["segments_changed"] == 0
    assert meta["segments_unchanged"] > 0
    print("✓ polish_status=no_change present in metadata for identical polish")


def test_polish_status_fallback_in_metadata():
    """When LLM is unreachable (fallback), metadata reports polish_status=fallback."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=True)
    original_stub = orch.polish_candidate_with_llm
    orch.polish_candidate_with_llm = stub_polish_candidate_fallback
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        orch.polish_candidate_with_llm = original_stub
    assert meta["strategy"] == "ja_audio_asr_mt"
    assert meta["polish_status"] == "fallback", meta
    print("✓ polish_status=fallback present in metadata for LLM fallback")


def test_no_polish_status_for_non_mt_strategies():
    """Strategies that don't run LLM polish should omit polish_status from metadata."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=False, jp_audio=False)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_en"
    assert "polish_status" not in meta, meta
    print("✓ polish_status absent for strategies that skip LLM polish")


if __name__ == "__main__":
    run_all_tests()
