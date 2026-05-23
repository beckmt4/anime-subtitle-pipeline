"""Tests for translation-memory dataset export helpers."""

from __future__ import annotations

import json

from core.translation import export_preference_pairs_jsonl, export_sft_dataset_jsonl


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_export_sft_dataset_jsonl_writes_messages_and_skips_invalid_records(tmp_path):
    output_path = tmp_path / "ja_en_subtitle_sft.jsonl"
    summary = export_sft_dataset_jsonl(
        [
            {
                "source_lang": "ja",
                "target_lang": "en",
                "domain": "anime",
                "source_text": "太郎は先輩です",
                "approved_translation": "Taro is a senpai.",
                "bad_translation": "He is my upperclassman.",
                "previous_context": "昨日の話だけど",
                "next_context": "よろしくお願いします",
                "tags": ["name_error"],
                "language_pack": "ja_en",
            },
            {
                "source_lang": "ja",
                "target_lang": "en",
                "source_text": "欠損テスト",
                "approved_translation": "",
            },
        ],
        output_path,
    )

    assert summary["written"] == 1
    assert summary["skipped"] == 1
    assert "approved_translation" in summary["skipped_records"][0]["reason"]

    rows = _read_jsonl(output_path)
    assert len(rows) == 1
    assert rows[0]["messages"][0]["role"] == "system"
    assert rows[0]["messages"][1]["content"].startswith("Context before: 昨日の話だけど")
    assert rows[0]["messages"][2]["content"] == "Taro is a senpai."
    assert rows[0]["metadata"]["source_lang"] == "ja"
    assert rows[0]["metadata"]["target_lang"] == "en"
    assert rows[0]["metadata"]["domain"] == "anime"
    assert rows[0]["metadata"]["tags"] == ["name_error"]


def test_export_preference_pairs_jsonl_writes_pairs_and_reports_missing_bad_translation(tmp_path):
    output_path = tmp_path / "ja_en_preference_pairs.jsonl"
    summary = export_preference_pairs_jsonl(
        [
            {
                "source_lang": "ja",
                "target_lang": "en",
                "domain": "anime",
                "source_text": "学園祭が始まる",
                "approved_translation": "The school festival starts.",
                "bad_translation": "The school event starts.",
                "tags": ["too_literal"],
            },
            {
                "source_lang": "ja",
                "target_lang": "en",
                "domain": "anime",
                "source_text": "行くぞ",
                "approved_translation": "Let's go.",
                "bad_translation": "",
            },
        ],
        output_path,
    )

    assert summary["written"] == 1
    assert summary["skipped"] == 1
    assert "bad_translation" in summary["skipped_records"][0]["reason"]

    rows = _read_jsonl(output_path)
    assert rows == [
        {
            "chosen_translation": "The school festival starts.",
            "domain": "anime",
            "reason": "approved human correction preserves meaning better",
            "rejected_translation": "The school event starts.",
            "source_lang": "ja",
            "source_text": "学園祭が始まる",
            "tags": ["too_literal"],
            "target_lang": "en",
        }
    ]
