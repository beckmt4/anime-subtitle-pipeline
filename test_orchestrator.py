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


def _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=False) -> MediaInfo:
    subs = []
    auds = []
    idx = 0
    if en_audio:
        auds.append(AudioStream(index=idx, codec="aac", language="en")); idx += 1
    if jp_audio:
        auds.append(AudioStream(index=idx, codec="aac", language="ja")); idx += 1
    sidx = 10
    if en_sub:
        subs.append(SubtitleStream(index=sidx, codec="subrip", language="en")); sidx += 1
    if jp_sub:
        subs.append(SubtitleStream(index=sidx, codec="subrip", language="ja")); sidx += 1
    return MediaInfo(path=Path("dummy.mkv"), format_name="matroska", duration=120.0, audio_streams=auds, subtitle_streams=subs)


def test_strategy_embedded_en():
    cfg = Config()
    media = _media(en_sub=True, en_audio=True, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_en", meta
    print("✓ embedded_en strategy chosen correctly")


def test_strategy_en_audio_when_no_en_sub_and_en_audio_preferred():
    cfg = Config()
    cfg._data.setdefault("generate", {})
    cfg._data["generate"]["prefer_subtitles"] = False
    cfg._data["generate"]["prefer_audio_language"] = "en"
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
    cfg._data.setdefault("generate", {})
    cfg._data["generate"]["prefer_subtitles"] = False
    cfg._data["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "en_audio_asr", meta
    print("✓ en_audio_asr fallback strategy chosen correctly")


def run_all_tests():
    test_strategy_embedded_en()
    test_strategy_en_audio_when_no_en_sub_and_en_audio_preferred()
    test_strategy_embedded_jp_mt()
    test_strategy_ja_audio_asr_mt()
    test_strategy_en_audio_fallback()
    print("\n✅ All orchestrator strategy tests PASSED")


if __name__ == "__main__":
    run_all_tests()
