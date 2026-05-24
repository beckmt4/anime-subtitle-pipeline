"""Tests for the packs/language/ja_en language pack.

Validates that the reference language pack meets the interface contract
defined in specs/29-language-pack-interface.md.
"""

from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# aliases
# ---------------------------------------------------------------------------

class TestJaEnAliases:
    def test_normalise_jpn(self):
        from packs.language.ja_en.aliases import normalise
        assert normalise("jpn") == "ja"

    def test_normalise_jp(self):
        from packs.language.ja_en.aliases import normalise
        assert normalise("jp") == "ja"

    def test_normalise_ja_jp(self):
        from packs.language.ja_en.aliases import normalise
        assert normalise("ja-jp") == "ja"

    def test_normalise_japanese(self):
        from packs.language.ja_en.aliases import normalise
        assert normalise("japanese") == "ja"

    def test_normalise_eng(self):
        from packs.language.ja_en.aliases import normalise
        assert normalise("eng") == "en"

    def test_normalise_en_us(self):
        from packs.language.ja_en.aliases import normalise
        assert normalise("en-us") == "en"

    def test_normalise_unknown_passthrough(self):
        from packs.language.ja_en.aliases import normalise
        assert normalise("unknown") == "unknown"

    def test_normalise_case_insensitive(self):
        from packs.language.ja_en.aliases import normalise
        assert normalise("JPN") == "ja"
        assert normalise("ENG") == "en"

    def test_lang_aliases_keys(self):
        from packs.language.ja_en.aliases import LANG_ALIASES
        assert "ja" in LANG_ALIASES
        assert "en" in LANG_ALIASES

    def test_ja_aliases_frozenset(self):
        from packs.language.ja_en.aliases import JA_ALIASES
        assert isinstance(JA_ALIASES, frozenset)
        assert "ja" in JA_ALIASES
        assert "jpn" in JA_ALIASES


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------

class TestJaEnPrompts:
    def test_get_system_prompt_natural(self):
        from packs.language.ja_en.prompts import get_system_prompt
        prompt = get_system_prompt("natural")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_get_system_prompt_literal(self):
        from packs.language.ja_en.prompts import get_system_prompt
        prompt = get_system_prompt("literal")
        assert isinstance(prompt, str)
        assert "honorific" in prompt.lower() or "honorific" in prompt

    def test_get_system_prompt_default_is_natural(self):
        from packs.language.ja_en.prompts import get_system_prompt
        assert get_system_prompt() == get_system_prompt("natural")

    def test_get_system_prompt_invalid_style_raises(self):
        from packs.language.ja_en.prompts import get_system_prompt
        with pytest.raises(ValueError):
            get_system_prompt("unknown_style")

    def test_get_user_prompt(self):
        from packs.language.ja_en.prompts import get_user_prompt
        result = get_user_prompt("Hello")
        assert "Hello" in result

    def test_natural_and_literal_differ(self):
        from packs.language.ja_en.prompts import get_system_prompt
        assert get_system_prompt("natural") != get_system_prompt("literal")

    @pytest.mark.parametrize("style", ["natural", "literal"])
    def test_pack_prompts_match_config_templates(self, style):
        from packs.language.ja_en.prompts import get_system_prompt

        config = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text(encoding="utf-8"))
        expected = config["llm"]["prompts"][style].format(
            max_lines=config["llm"]["max_lines"],
            max_chars_per_line=config["llm"]["max_chars_per_line"],
        )
        assert get_system_prompt(style).strip() == expected.strip()


# ---------------------------------------------------------------------------
# cjk_filter
# ---------------------------------------------------------------------------

class TestCjkFilter:
    def test_has_cjk_leak_true(self):
        from packs.language.ja_en.cjk_filter import has_cjk_leak
        assert has_cjk_leak("こんにちはHello") is True

    def test_has_cjk_leak_false(self):
        from packs.language.ja_en.cjk_filter import has_cjk_leak
        assert has_cjk_leak("Hello there") is False

    def test_has_cjk_leak_kanji(self):
        from packs.language.ja_en.cjk_filter import has_cjk_leak
        assert has_cjk_leak("日本語") is True

    def test_recover_leading_english_mixed(self):
        from packs.language.ja_en.cjk_filter import recover_leading_english
        result = recover_leading_english("こんにちはHello there")
        assert result == "Hello there"

    def test_recover_leading_english_pure_english(self):
        from packs.language.ja_en.cjk_filter import recover_leading_english
        assert recover_leading_english("Hello there") == "Hello there"

    def test_recover_leading_english_pure_cjk_returns_original(self):
        from packs.language.ja_en.cjk_filter import recover_leading_english
        original = "日本語"
        result = recover_leading_english(original)
        # When no English portion exists, original should be returned
        assert result == original

    def test_filter_candidate_cjk_mixed_list(self):
        from packs.language.ja_en.cjk_filter import filter_candidate_cjk
        inputs = ["Hello", "こんにちはGoodbye", "Normal text"]
        result = filter_candidate_cjk(inputs)
        assert result[0] == "Hello"
        assert result[1] == "Goodbye"
        assert result[2] == "Normal text"

    def test_filter_candidate_cjk_empty_list(self):
        from packs.language.ja_en.cjk_filter import filter_candidate_cjk
        assert filter_candidate_cjk([]) == []


# ---------------------------------------------------------------------------
# pack-level metadata
# ---------------------------------------------------------------------------

class TestJaEnPackMetadata:
    def test_source_lang(self):
        from packs.language.ja_en import SOURCE_LANG
        assert SOURCE_LANG == "ja"

    def test_target_lang(self):
        from packs.language.ja_en import TARGET_LANG
        assert TARGET_LANG == "en"

    def test_pack_id(self):
        from packs.language.ja_en import PACK_ID
        assert PACK_ID == "ja_en"

    def test_pack_glossary_name_and_style_files_exist(self):
        pack_dir = Path(__file__).parent.parent / "packs" / "language" / "ja_en"
        assert (pack_dir / "glossary.yml").exists()
        assert (pack_dir / "names.yml").exists()
        assert (pack_dir / "style.yml").exists()


class TestJaEnRoutingHooks:
    def test_load_language_routing_hooks(self):
        from packs.language import load_language_routing_hooks

        hooks = load_language_routing_hooks("ja", "en")

        assert hooks.pack_id == "ja_en"
        assert hooks.source_language == "ja"
        assert hooks.target_language == "en"
        assert hooks.untagged_audio_fallback_source_language == "ja"
        assert "ja" in hooks.lang_aliases
        assert "en" in hooks.lang_aliases
        assert callable(hooks.translate_candidate)

    def test_routing_translate_candidate_delegates_to_pack_workflow(self, monkeypatch):
        from packs.language.ja_en import routing

        calls = []

        def fake_translate(candidate, cfg, ja_candidate=None):
            calls.append((candidate, cfg, ja_candidate))
            return "translated"

        monkeypatch.setattr(routing, "translate_candidate_jp_to_en_workflow", fake_translate)

        result = routing.translate_candidate("candidate", "cfg", "source")

        assert result == "translated"
        assert calls == [("candidate", "cfg", "source")]


# ---------------------------------------------------------------------------
# language pack registry
# ---------------------------------------------------------------------------

class TestLanguagePackRegistry:
    def test_list_available_packs_returns_ja_en(self):
        from packs.language import list_available_packs
        packs = list_available_packs()
        assert "ja_en" in packs

    def test_list_available_packs_returns_list(self):
        from packs.language import list_available_packs
        packs = list_available_packs()
        assert isinstance(packs, list)

    def test_list_available_packs_sorted(self):
        from packs.language import list_available_packs
        packs = list_available_packs()
        assert packs == sorted(packs)

    def test_load_language_routing_hooks_unknown_pair_raises_value_error(self):
        from packs.language import load_language_routing_hooks
        with pytest.raises(ValueError, match="No language-pack routing hooks"):
            load_language_routing_hooks("zz", "xx")

    def test_list_available_packs_and_load_are_consistent(self):
        """Every pack returned by list_available_packs() must be loadable."""
        from packs.language import list_available_packs, load_language_routing_hooks

        for pack_id in list_available_packs():
            src, tgt = pack_id.split("_", 1)
            hooks = load_language_routing_hooks(src, tgt)
            assert hooks.pack_id == pack_id
