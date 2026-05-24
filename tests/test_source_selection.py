"""Unit tests for orchestrator source-selection helpers.

Tests _lang_matches, _first_text_sub, _first_audio_order, and
_select_untagged_audio_fallback — the pure decision logic that drives
run_generate — without calling any live services.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime.orchestrator import _lang_matches, _first_text_sub, _first_audio_order, _select_untagged_audio_fallback
import core.runtime.orchestrator as orch
from core.media import MediaInfo, AudioStream, SubtitleStream
from packs.language.ja_en.aliases import LANG_ALIASES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_media(
    audio_langs: list = None,
    sub_specs: list = None,
) -> MediaInfo:
    """Build a MediaInfo with audio and subtitle streams from simple specs.

    audio_langs: list of raw language tag strings, e.g. ["jpn", "eng"]
    sub_specs: list of (lang, codec) tuples, e.g. [("eng", "subrip")]
    """
    audio_streams = []
    for i, lang in enumerate(audio_langs or []):
        audio_streams.append(
            AudioStream(index=i, codec="aac", language=lang, raw_language=lang)
        )

    subtitle_streams = []
    offset = len(audio_streams)
    for i, (lang, codec) in enumerate(sub_specs or []):
        is_bitmap = codec in {"dvd_subtitle", "pgssub", "xsub"}
        subtitle_streams.append(
            SubtitleStream(
                index=i + offset,
                codec=codec,
                language=lang,
                raw_language=lang,
                is_bitmap=is_bitmap,
            )
        )

    return MediaInfo(
        path=Path("test.mkv"),
        format_name="matroska",
        duration=1440.0,
        audio_streams=audio_streams,
        subtitle_streams=subtitle_streams,
    )


# ---------------------------------------------------------------------------
# _lang_matches
# ---------------------------------------------------------------------------

class TestLangMatches:
    def test_orchestrator_uses_pack_lang_aliases(self):
        assert orch._LANG_ALIASES is LANG_ALIASES

    @pytest.mark.parametrize("code", ["ja", "jpn", "jp", "ja-jp"])
    def test_ja_variants_match_ja(self, code):
        assert _lang_matches(code, "ja") is True

    @pytest.mark.parametrize("code", ["en", "eng", "en-us", "en-gb"])
    def test_en_variants_match_en(self, code):
        assert _lang_matches(code, "en") is True

    def test_none_does_not_match(self):
        assert _lang_matches(None, "ja") is False

    def test_empty_string_does_not_match(self):
        assert _lang_matches("", "ja") is False

    @pytest.mark.parametrize("code", ["JPN", "Jpn", "JA-JP"])
    def test_matching_is_case_insensitive(self, code):
        assert _lang_matches(code, "ja") is True

    def test_unrelated_lang_does_not_match_ja(self):
        assert _lang_matches("fra", "ja") is False

    def test_unrelated_lang_does_not_match_en(self):
        assert _lang_matches("zho", "en") is False

    def test_unknown_target_uses_exact_match_fallback(self):
        # For a target not in _LANG_ALIASES, the set {target} is used
        assert _lang_matches("zz", "zz") is True
        assert _lang_matches("ja", "zz") is False

    # --- BCP-47 regional subtag tests ---

    @pytest.mark.parametrize("code", ["en-AU", "en-CA", "en-IE", "en-NZ", "en-IN"])
    def test_bcp47_en_regional_variants_match_en(self, code):
        """BCP-47 regional English codes not in the alias list must still match."""
        assert _lang_matches(code, "en") is True

    @pytest.mark.parametrize("code", ["ja-Latn", "ja-JP"])
    def test_bcp47_ja_regional_variants_match_ja(self, code):
        """BCP-47 Japanese subtags must still match."""
        assert _lang_matches(code, "ja") is True

    def test_bcp47_prefix_does_not_cause_false_positive(self):
        """'fr-CA' must not match 'en'."""
        assert _lang_matches("fr-CA", "en") is False


# ---------------------------------------------------------------------------
# _first_text_sub
# ---------------------------------------------------------------------------

class TestFirstTextSub:
    def test_finds_en_text_subtitle(self):
        media = make_media(sub_specs=[("en", "subrip")])
        idx = _first_text_sub(media, "en")
        assert idx == 0  # stream index assigned by make_media

    def test_finds_ja_text_subtitle_by_jpn_tag(self):
        media = make_media(sub_specs=[("jpn", "ass")])
        idx = _first_text_sub(media, "ja")
        assert idx == 0

    def test_skips_bitmap_subtitles(self):
        # bitmap sub comes first, text sub second; should return text sub's index
        media = make_media(sub_specs=[("en", "dvd_subtitle"), ("en", "subrip")])
        idx = _first_text_sub(media, "en")
        assert idx == 1

    def test_bitmap_only_returns_none(self):
        media = make_media(sub_specs=[("en", "pgssub")])
        assert _first_text_sub(media, "en") is None

    def test_returns_none_when_no_matching_language(self):
        media = make_media(sub_specs=[("ja", "subrip")])
        assert _first_text_sub(media, "en") is None

    def test_returns_none_with_no_subtitle_streams(self):
        media = make_media(audio_langs=["ja"])
        assert _first_text_sub(media, "en") is None

    def test_returns_first_match_when_multiple(self):
        media = make_media(sub_specs=[("en", "subrip"), ("en", "ass")])
        idx = _first_text_sub(media, "en")
        assert idx == 0  # first matching stream

    # --- Regression: real-world tag variants ---

    def test_finds_en_by_eng_tag(self):
        """Regression: 'eng' (ISO 639-2) tagged subtitle must be detected as English."""
        media = make_media(sub_specs=[("eng", "subrip")])
        idx = _first_text_sub(media, "en")
        assert idx is not None, "Expected to find English subtitle tagged 'eng'"

    def test_finds_en_by_bcp47_en_us_tag(self):
        """Regression (Once Upon a Crime): 'en-US' BCP-47 tag must be detected as English."""
        media = make_media(sub_specs=[("en-US", "subrip")])
        idx = _first_text_sub(media, "en")
        assert idx is not None, "Expected to find English subtitle tagged 'en-US'"

    def test_couple_of_cuckoos_regression(self):
        """Regression: bitmap JA sub first, text EN sub (eng tag) second — must find EN."""
        media = make_media(sub_specs=[("jpn", "pgssub"), ("eng", "subrip")])
        idx = _first_text_sub(media, "en")
        assert idx is not None, "Expected to find English text subtitle after skipping bitmap JA"
        # stream indexes: 0=jpn/pgssub, 1=eng/subrip → index 1
        assert idx == 1

    def test_once_upon_a_crime_regression(self):
        """Regression: JA subs followed by en-US BCP-47 tagged sub — must find EN."""
        media = make_media(
            audio_langs=["jpn"],
            sub_specs=[("jpn", "pgssub"), ("jpn", "subrip"), ("en-US", "subrip")],
        )
        idx = _first_text_sub(media, "en")
        assert idx is not None, "Expected to find English subtitle tagged 'en-US'"


# ---------------------------------------------------------------------------
# _first_audio_order
# ---------------------------------------------------------------------------

class TestFirstAudioOrder:
    def test_finds_ja_audio_at_correct_order(self):
        media = make_media(audio_langs=["en", "ja"])
        # audio order 0 = en, order 1 = ja
        assert _first_audio_order(media, "ja") == 1

    def test_finds_en_audio_at_correct_order(self):
        media = make_media(audio_langs=["ja", "en"])
        assert _first_audio_order(media, "en") == 1

    def test_finds_first_stream_when_first_matches(self):
        media = make_media(audio_langs=["ja", "en"])
        assert _first_audio_order(media, "ja") == 0

    def test_returns_none_when_no_match(self):
        media = make_media(audio_langs=["en", "fr"])
        assert _first_audio_order(media, "ja") is None

    def test_returns_none_with_no_audio_streams(self):
        media = make_media()
        assert _first_audio_order(media, "ja") is None

    def test_jpn_tag_matches_ja_target(self):
        media = make_media(audio_langs=["jpn"])
        assert _first_audio_order(media, "ja") == 0

    def test_eng_tag_matches_en_target(self):
        media = make_media(audio_langs=["eng"])
        assert _first_audio_order(media, "en") == 0


# ---------------------------------------------------------------------------
# _select_untagged_audio_fallback
# ---------------------------------------------------------------------------

def _make_audio_stream(
    index: int,
    channels: int = 2,
    language: str | None = None,
    raw_language: str | None = None,
    title: str | None = None,
) -> AudioStream:
    """Build an AudioStream with optional title tag for heuristic tests."""
    tags: dict[str, str] = {}
    if title is not None:
        tags["title"] = title
    return AudioStream(
        index=index,
        codec="aac",
        channels=channels,
        sample_rate=48000,
        language=language,
        raw_language=raw_language,
        tags=tags,
    )


def _make_untagged_media(*streams: AudioStream) -> MediaInfo:
    m = MediaInfo(path=Path("dummy.mkv"), format_name="matroska", duration=None)
    m.audio_streams.extend(streams)
    return m


class TestSelectUntaggedAudioFallback:
    def test_single_stereo_track_returns_order_0(self):
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=2),
        )
        order, reason = _select_untagged_audio_fallback(media)
        assert order == 0
        assert "stereo" in reason.lower() or "2-channel" in reason.lower()

    def test_japanese_title_keyword_wins_over_stereo(self):
        """A track with a Japanese title tag should be preferred over plain stereo."""
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=2),           # stereo, no title
            _make_audio_stream(index=1, channels=2, title="Japanese Audio"),
        )
        order, reason = _select_untagged_audio_fallback(media)
        assert order == 1
        assert "japanese" in reason.lower() or "title" in reason.lower()

    def test_jpn_title_keyword_detected(self):
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=2),
            _make_audio_stream(index=1, channels=2, title="JPN"),
        )
        order, _ = _select_untagged_audio_fallback(media)
        assert order == 1

    def test_nihongo_title_keyword_detected(self):
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=2),
            _make_audio_stream(index=1, channels=2, title="日本語"),
        )
        order, _ = _select_untagged_audio_fallback(media)
        assert order == 1

    def test_title_keyword_match_is_case_insensitive(self):
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=2, title="JAPANESE AUDIO"),
        )
        order, _ = _select_untagged_audio_fallback(media)
        assert order == 0

    def test_first_stereo_when_no_japanese_title(self):
        """Without a Japanese title keyword, first stereo track wins."""
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=1),   # mono
            _make_audio_stream(index=1, channels=2),   # stereo → should win
            _make_audio_stream(index=2, channels=6),   # 5.1 surround
        )
        order, reason = _select_untagged_audio_fallback(media)
        assert order == 1
        assert "stereo" in reason.lower() or "2-channel" in reason.lower()

    def test_track_0_fallback_when_all_mono(self):
        """No stereo, no title → default to track 0."""
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=1),
            _make_audio_stream(index=1, channels=1),
        )
        order, reason = _select_untagged_audio_fallback(media)
        assert order == 0
        assert "default" in reason.lower() or "first" in reason.lower()

    def test_und_tagged_track_still_selectable(self):
        """Tracks tagged 'und' (undefined) are still valid fallback candidates."""
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=2, language="und", raw_language="und"),
        )
        order, _ = _select_untagged_audio_fallback(media)
        assert order == 0

    def test_multiple_stereo_returns_first(self):
        """When multiple stereo tracks exist and no title matches, return the first."""
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=2),
            _make_audio_stream(index=1, channels=2),
        )
        order, _ = _select_untagged_audio_fallback(media)
        assert order == 0

    def test_stereo_before_title_match_when_at_lower_index(self):
        """Title keyword at a HIGHER index still wins over a plain stereo track."""
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=2),           # stereo, no title
            _make_audio_stream(index=1, channels=1, title="Japanese"),  # mono with title
        )
        order, _ = _select_untagged_audio_fallback(media)
        # Title heuristic has higher priority than stereo channel heuristic
        assert order == 1

    def test_mixed_language_mul_tag_treated_as_fallback(self):
        """A track tagged 'mul' (multiple languages) is treated like untagged."""
        media = _make_untagged_media(
            _make_audio_stream(index=0, channels=1, language="mul", raw_language="mul"),
            _make_audio_stream(index=1, channels=2, title="Japanese"),
        )
        order, _ = _select_untagged_audio_fallback(media)
        # Title wins regardless of the 'mul' tag on track 0
        assert order == 1
