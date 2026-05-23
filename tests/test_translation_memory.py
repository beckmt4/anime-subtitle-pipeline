"""Tests for local translation memory add/query/export behavior."""

from __future__ import annotations

import json

from core.translation import TranslationMemoryStore, build_prompt_memory_block


def test_translation_memory_add_query_export(tmp_path):
    memory_path = tmp_path / "translation_memory.jsonl"
    export_path = tmp_path / "anime_export.jsonl"
    store = TranslationMemoryStore(memory_path)

    store.add(
        {
            "source_lang": "ja",
            "target_lang": "en",
            "domain": "anime",
            "source_text": "太郎は先輩です",
            "bad_translation": "He is my upperclassman.",
            "approved_translation": "Taro is a senpai.",
            "tags": ["name_error"],
            "notes": "human-approved",
            "language_pack": "ja_en",
        }
    )
    store.add(
        {
            "source_lang": "ja",
            "target_lang": "en",
            "domain": "anime",
            "source_text": "学園祭が始まる",
            "bad_translation": "The school event starts.",
            "approved_translation": "The school festival starts.",
            "tags": ["too_literal"],
            "language_pack": "ja_en",
        }
    )
    store.add(
        {
            "source_lang": "ja",
            "target_lang": "en",
            "domain": "jav",
            "source_text": "やめて",
            "bad_translation": "Please stop.",
            "approved_translation": "Stop it.",
            "language_pack": "ja_en",
        }
    )

    results = store.query(
        source_text="太郎は先輩です",
        source_lang="ja",
        target_lang="en",
        domain="anime",
        language_pack="ja_en",
        limit=2,
    )

    assert len(results) == 1
    assert results[0]["source_text"] == "太郎は先輩です"
    assert results[0]["approved_translation"] == "Taro is a senpai."
    assert all(item["domain"] == "anime" for item in results)

    exported_count = store.export_jsonl(export_path, source_lang="ja", target_lang="en", domain="anime")
    assert exported_count == 2
    lines = [line for line in export_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payloads = [json.loads(line) for line in lines]
    assert len(payloads) == 2
    assert {entry["domain"] for entry in payloads} == {"anime"}


def test_build_prompt_memory_block_formats_entries():
    block = build_prompt_memory_block(
        [
            {
                "source_text": "太郎は先輩です",
                "bad_translation": "He is my upperclassman.",
                "approved_translation": "Taro is a senpai.",
            }
        ]
    )
    assert "Approved translation memory" in block
    assert "Source: 太郎は先輩です" in block
    assert "Approved: Taro is a senpai." in block
    assert "Avoid: He is my upperclassman." in block
