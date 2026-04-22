"""Tests for the domain packs (packs/domain/anime and packs/domain/jav).

Validates that both reference domain packs meet the interface contract
defined in specs/30-domain-pack-interface.md.
"""

import pytest


# ---------------------------------------------------------------------------
# anime pack
# ---------------------------------------------------------------------------

class TestAnimePack:
    def test_domain_id(self):
        from packs.domain.anime import DOMAIN_ID
        assert DOMAIN_ID == "anime"

    def test_style_config_returns_dict(self):
        from packs.domain.anime.style import get_style_config
        cfg = get_style_config()
        assert isinstance(cfg, dict)

    def test_style_config_required_keys(self):
        from packs.domain.anime.style import get_style_config
        cfg = get_style_config()
        assert "max_chars_per_line" in cfg
        assert "max_lines_per_segment" in cfg
        assert "llm_style" in cfg

    def test_style_config_llm_style_is_natural(self):
        from packs.domain.anime.style import get_style_config
        assert get_style_config()["llm_style"] == "natural"

    def test_style_config_preserve_honorifics(self):
        from packs.domain.anime.style import get_style_config
        cfg = get_style_config()
        assert cfg.get("preserve_honorifics") is True

    def test_style_config_max_chars_per_line_is_int(self):
        from packs.domain.anime.style import get_style_config
        cfg = get_style_config()
        assert isinstance(cfg["max_chars_per_line"], int)
        assert cfg["max_chars_per_line"] > 0

    def test_style_config_returns_new_copy(self):
        """Mutating the returned dict must not affect the module default."""
        from packs.domain.anime.style import get_style_config
        cfg1 = get_style_config()
        cfg1["max_chars_per_line"] = 999
        cfg2 = get_style_config()
        assert cfg2["max_chars_per_line"] != 999

    def test_no_requires_opt_in(self):
        """Anime pack should not require opt-in (it is safe content)."""
        import packs.domain.anime as anime_pack
        opt_in = getattr(anime_pack, "REQUIRES_OPT_IN", False)
        assert opt_in is False


# ---------------------------------------------------------------------------
# jav pack
# ---------------------------------------------------------------------------

class TestJavPack:
    def test_domain_id(self):
        from packs.domain.jav import DOMAIN_ID
        assert DOMAIN_ID == "jav"

    def test_requires_opt_in(self):
        from packs.domain.jav import REQUIRES_OPT_IN
        assert REQUIRES_OPT_IN is True

    def test_assert_opt_in_passes_when_true(self):
        from packs.domain.jav.privacy import assert_opt_in
        assert_opt_in(True)  # should not raise

    def test_assert_opt_in_raises_when_false(self):
        from packs.domain.jav.privacy import assert_opt_in, ContentGateError
        with pytest.raises(ContentGateError):
            assert_opt_in(False)

    def test_content_gate_error_is_runtime_error(self):
        from packs.domain.jav.privacy import ContentGateError
        assert issubclass(ContentGateError, RuntimeError)

    def test_redact_metadata_file_path(self):
        from packs.domain.jav.privacy import redact_metadata
        meta = {"file": "/path/to/video.mp4", "duration": 90.0}
        result = redact_metadata(meta)
        assert result["file"] == "<redacted>"
        assert result["duration"] == 90.0

    def test_redact_metadata_video_path(self):
        from packs.domain.jav.privacy import redact_metadata
        meta = {"video_path": "/secret/video.mp4"}
        assert redact_metadata(meta)["video_path"] == "<redacted>"

    def test_redact_metadata_non_sensitive_preserved(self):
        from packs.domain.jav.privacy import redact_metadata
        meta = {"language": "ja", "segment_count": 100}
        result = redact_metadata(meta)
        assert result["language"] == "ja"
        assert result["segment_count"] == 100

    def test_redact_metadata_returns_new_dict(self):
        """Must not mutate the original metadata dict."""
        from packs.domain.jav.privacy import redact_metadata
        original = {"file": "/path/video.mp4", "duration": 30}
        redact_metadata(original)
        assert original["file"] == "/path/video.mp4"

    def test_redact_metadata_empty_dict(self):
        from packs.domain.jav.privacy import redact_metadata
        assert redact_metadata({}) == {}
