"""Test audio track selection via `choose_audio_track` with synthetic MediaInfo."""

from media_inspect import MediaInfo, AudioStream, choose_audio_track
from pathlib import Path


class DummyAudio(AudioStream):
    pass


def build_media() -> MediaInfo:
    m = MediaInfo(path=Path("dummy.mkv"), format_name="matroska", duration=None)
    # global stream indices arbitrary
    m.audio_streams.append(AudioStream(index=0, codec="aac", channels=2, sample_rate=48000, language="en", raw_language="eng"))
    m.audio_streams.append(AudioStream(index=1, codec="aac", channels=2, sample_rate=48000, language="ja", raw_language="jpn"))
    m.audio_streams.append(AudioStream(index=2, codec="aac", channels=2, sample_rate=48000, language="fr", raw_language="fre"))
    return m


def test_choose_pref_ja():
    media = build_media()
    idx = choose_audio_track(media, ["ja", "en"])  # ja should be second (audio-order 1)
    assert idx == 1, f"Expected 1 for Japanese track, got {idx}"


def test_fallback_first():
    media = build_media()
    idx = choose_audio_track(media, ["zh"])  # no match -> fallback 0
    assert idx == 0, f"Expected fallback 0, got {idx}"


if __name__ == "__main__":
    test_choose_pref_ja()
    test_fallback_first()
    print("Audio selection tests passed")
