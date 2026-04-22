"""Unit tests for media_inspect — language normalization, ffprobe parsing, stream detection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from media_inspect import (
    _norm_lang,
    AudioStream,
    SubtitleStream,
    MediaInfo,
    inspect_media,
    choose_audio_track,
)

FFPROBE_FIXTURES = Path(__file__).parent.parent / "fixtures" / "ffprobe"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_run(stdout: str) -> MagicMock:
    result = MagicMock()
    result.stdout = stdout
    result.stderr = ""
    result.returncode = 0
    return result


# ---------------------------------------------------------------------------
# Language normalization
# ---------------------------------------------------------------------------

class TestNormLang:
    @pytest.mark.parametrize("code,expected", [
        ("jpn", "ja"),
        ("ja", "ja"),
        ("japanese", "ja"),
        ("eng", "en"),
        ("en", "en"),
        ("english", "en"),
        ("fre", "fr"),
        ("fra", "fr"),
        ("french", "fr"),
        ("chi", "zh"),
        ("zho", "zh"),
        ("chinese", "zh"),
        ("und", "und"),
    ])
    def test_known_codes_map_correctly(self, code, expected):
        assert _norm_lang(code) == expected

    def test_unknown_code_is_lowercased_passthrough(self):
        assert _norm_lang("SPA") == "spa"

    def test_none_returns_none(self):
        assert _norm_lang(None) is None

    def test_empty_string_returns_none(self):
        assert _norm_lang("") is None

    @pytest.mark.parametrize("code", ["JPN", "Jpn", "JPN"])
    def test_case_insensitive(self, code):
        assert _norm_lang(code) == "ja"

    def test_full_name_english_normalizes_to_en(self):
        assert _norm_lang("English") == "en"

    def test_full_name_japanese_normalizes_to_ja(self):
        assert _norm_lang("Japanese") == "ja"


# ---------------------------------------------------------------------------
# ffprobe JSON parsing — happy path
# ---------------------------------------------------------------------------

class TestInspectMediaParsing:
    @patch("media_inspect.subprocess.run")
    def test_minimal_ja_audio(self, mock_run, tmp_path):
        video = tmp_path / "test.mkv"
        video.write_bytes(b"")
        mock_run.return_value = _mock_run(
            (FFPROBE_FIXTURES / "minimal_ja_audio.json").read_text(encoding="utf-8")
        )
        info = inspect_media(str(video))

        assert info.format_name == "matroska,webm"
        assert info.duration == pytest.approx(1440.12, abs=0.01)
        assert len(info.audio_streams) == 1
        assert info.audio_streams[0].language == "ja"
        assert info.audio_streams[0].codec == "aac"
        assert info.audio_streams[0].channels == 2
        assert info.audio_streams[0].sample_rate == 48000
        assert len(info.subtitle_streams) == 0

    @patch("media_inspect.subprocess.run")
    def test_multi_stream_audio_and_subtitle_counts(self, mock_run, tmp_path):
        video = tmp_path / "test.mkv"
        video.write_bytes(b"")
        mock_run.return_value = _mock_run(
            (FFPROBE_FIXTURES / "multi_stream.json").read_text(encoding="utf-8")
        )
        info = inspect_media(str(video))

        assert len(info.audio_streams) == 2
        assert info.audio_streams[0].language == "ja"
        assert info.audio_streams[1].language == "en"

        assert len(info.subtitle_streams) == 2
        assert info.subtitle_streams[0].language == "en"
        assert info.subtitle_streams[0].is_bitmap is False
        assert info.subtitle_streams[1].language == "ja"
        assert info.subtitle_streams[1].is_bitmap is True  # dvd_subtitle

    @patch("media_inspect.subprocess.run")
    def test_subprocess_called_as_list_not_shell_string(self, mock_run, tmp_path):
        """ffprobe must be invoked as a list to prevent shell injection."""
        video = tmp_path / "test.mkv"
        video.write_bytes(b"")
        mock_run.return_value = _mock_run(
            (FFPROBE_FIXTURES / "minimal_ja_audio.json").read_text(encoding="utf-8")
        )
        inspect_media(str(video))
        cmd = mock_run.call_args[0][0]
        assert isinstance(cmd, list)
        assert cmd[0] == "ffprobe"

    @patch("media_inspect.subprocess.run")
    def test_couple_of_cuckoos_fixture_en_sub_detected(self, mock_run, tmp_path):
        """Regression: file with JA audio, bitmap JA sub, and text EN sub (eng tag)."""
        video = tmp_path / "cuckoos.mkv"
        video.write_bytes(b"")
        mock_run.return_value = _mock_run(
            (FFPROBE_FIXTURES / "couple_of_cuckoos_s01e01.json").read_text(encoding="utf-8")
        )
        info = inspect_media(str(video))

        assert len(info.audio_streams) == 1
        assert info.audio_streams[0].language == "ja"

        assert len(info.subtitle_streams) == 2
        # stream index 1: bitmap JA (pgssub)
        assert info.subtitle_streams[0].is_bitmap is True
        assert info.subtitle_streams[0].language == "ja"
        # stream index 2: text EN (subrip, tagged "eng")
        assert info.subtitle_streams[1].is_bitmap is False
        assert info.subtitle_streams[1].language == "en"

    @patch("media_inspect.subprocess.run")
    def test_once_upon_a_crime_fixture_en_sub_detected(self, mock_run, tmp_path):
        """Regression: file with JA audio, JA subs, and a BCP-47 'en-US' text sub."""
        video = tmp_path / "crime.mkv"
        video.write_bytes(b"")
        mock_run.return_value = _mock_run(
            (FFPROBE_FIXTURES / "once_upon_a_crime.json").read_text(encoding="utf-8")
        )
        info = inspect_media(str(video))

        assert len(info.audio_streams) == 1
        assert info.audio_streams[0].language == "ja"

        assert len(info.subtitle_streams) == 3
        # The last subtitle stream is tagged "en-US" — raw_language preserved
        en_sub = info.subtitle_streams[2]
        assert en_sub.is_bitmap is False
        assert en_sub.raw_language == "en-US"


# ---------------------------------------------------------------------------
# Bitmap subtitle detection
# ---------------------------------------------------------------------------

class TestBitmapSubtitleDetection:
    def _make_data(self, codec: str) -> str:
        return json.dumps({
            "streams": [{
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": codec,
                "tags": {"language": "jpn"},
            }],
            "format": {"format_name": "matroska", "duration": "60.0"},
        })

    @pytest.mark.parametrize("codec", ["dvd_subtitle", "pgssub", "xsub"])
    def test_bitmap_codecs_flagged(self, codec, tmp_path):
        video = tmp_path / "test.mkv"
        video.write_bytes(b"")
        with patch("media_inspect.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(self._make_data(codec))
            info = inspect_media(str(video))
        assert info.subtitle_streams[0].is_bitmap is True

    @pytest.mark.parametrize("codec", ["subrip", "ass", "webvtt"])
    def test_text_codecs_not_bitmap(self, codec, tmp_path):
        video = tmp_path / "test.mkv"
        video.write_bytes(b"")
        with patch("media_inspect.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(self._make_data(codec))
            info = inspect_media(str(video))
        assert info.subtitle_streams[0].is_bitmap is False


# ---------------------------------------------------------------------------
# Failure cases
# ---------------------------------------------------------------------------

class TestInspectMediaFailures:
    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            inspect_media(str(tmp_path / "does_not_exist.mkv"))

    @patch("media_inspect.subprocess.run")
    def test_ffprobe_failure_raises_runtime_error(self, mock_run, tmp_path):
        video = tmp_path / "test.mkv"
        video.write_bytes(b"")
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["ffprobe"], stderr="ffprobe error"
        )
        with pytest.raises(RuntimeError, match="ffprobe failed"):
            inspect_media(str(video))

    @patch("media_inspect.subprocess.run")
    def test_invalid_json_raises_runtime_error(self, mock_run, tmp_path):
        video = tmp_path / "test.mkv"
        video.write_bytes(b"")
        mock_run.return_value = _mock_run("not valid json {{")
        with pytest.raises(RuntimeError, match="Failed to parse ffprobe JSON"):
            inspect_media(str(video))


# ---------------------------------------------------------------------------
# choose_audio_track
# ---------------------------------------------------------------------------

def _make_media_with_audio(langs: list) -> MediaInfo:
    streams = [
        AudioStream(
            index=i,
            codec="aac",
            language=_norm_lang(lang),
            raw_language=lang,
        )
        for i, lang in enumerate(langs)
    ]
    return MediaInfo(
        path=Path("test.mkv"),
        format_name="matroska",
        duration=60.0,
        audio_streams=streams,
    )


class TestChooseAudioTrack:
    def test_selects_preferred_ja_track(self):
        media = _make_media_with_audio(["eng", "jpn"])
        assert choose_audio_track(media, preferred_languages=["ja"]) == 1

    def test_falls_back_to_first_when_no_preferred_match(self):
        media = _make_media_with_audio(["eng", "fra"])
        assert choose_audio_track(media, preferred_languages=["ja"]) == 0

    def test_empty_streams_returns_zero(self):
        media = MediaInfo(path=Path("test.mkv"), format_name="matroska", duration=60.0)
        assert choose_audio_track(media) == 0

    def test_jpn_code_in_preferred_matches_normalized_ja_stream(self):
        """'jpn' in the preferred list must match a stream normalized to 'ja'."""
        media = _make_media_with_audio(["eng", "jpn"])
        assert choose_audio_track(media, preferred_languages=["jpn"]) == 1

    def test_priority_order_respected(self):
        media = _make_media_with_audio(["eng", "jpn", "fra"])
        # prefer en first — should pick index 0
        assert choose_audio_track(media, preferred_languages=["en", "ja"]) == 0
