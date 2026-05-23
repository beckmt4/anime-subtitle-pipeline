"""Tests for core.translation.glossary helpers."""

from __future__ import annotations

from core.translation import (
    build_prompt_glossary_block,
    load_active_glossary_data,
    validate_required_term_drift,
)


class DummyConfig:
    def __init__(self, *, domain_pack: str | None = None, data=None):
        self.domain_pack = domain_pack
        self._data = data or {}

    def get(self, *keys, default=None):
        value = self._data
        for key in keys:
            if not isinstance(value, dict):
                return default
            value = value.get(key)
            if value is None:
                return default
        return value


def test_load_active_glossary_data_domain_overrides_language_term():
    cfg = DummyConfig(domain_pack="anime", data={"asr": {"language": "ja"}})

    glossary = load_active_glossary_data(cfg)
    by_kind_source = {(entry["kind"], entry["source"]): entry for entry in glossary["entries"]}

    assert glossary["language_pack"] == "ja_en"
    assert glossary["domain_pack"] == "anime"
    assert by_kind_source[("term", "先輩")]["target"] == "senpai"
    assert by_kind_source[("term", "先輩")]["scope"] == "domain"


def test_build_prompt_glossary_block_includes_only_relevant_entries():
    cfg = DummyConfig(domain_pack="anime", data={"asr": {"language": "ja"}})
    glossary = load_active_glossary_data(cfg)

    block = build_prompt_glossary_block("太郎は先輩です。", glossary)

    assert "Glossary enforcement" in block
    assert "太郎 -> Taro" in block
    assert "先輩 -> senpai" in block
    assert "学園祭 -> school festival" not in block


def test_validate_required_term_drift_detects_name_and_honorific():
    cfg = DummyConfig(domain_pack="anime", data={"asr": {"language": "ja"}})
    glossary = load_active_glossary_data(cfg)

    findings = validate_required_term_drift(
        source_text="太郎は先輩です。",
        final_text="He is my upperclassman.",
        glossary_data=glossary,
    )

    codes = {finding["code"] for finding in findings}
    assert "bad_name" in codes
    assert "bad_honorific" in codes
