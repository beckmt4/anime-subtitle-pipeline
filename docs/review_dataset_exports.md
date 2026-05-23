# Review correction dataset exports

Use `scripts/export_review_corrections.py` to convert approved local review edits
(stored in translation memory) into benchmark and training JSONL datasets.

## Command

```bash
python scripts/export_review_corrections.py \
  --memory-path outbox/translation_memory.jsonl \
  --approved-output artifacts/review_exports/approved_corrections.jsonl \
  --benchmark-output fixtures/translation_eval/approved_references.jsonl \
  --sft-output artifacts/training/ja_en_subtitle_sft.jsonl \
  --preference-output artifacts/training/ja_en_preference_pairs.jsonl \
  --source-lang ja --target-lang en --domain anime
```

## Output formats

### Approved corrections

`artifacts/review_exports/approved_corrections.jsonl`

- Normalized correction records from translation memory.
- Includes source text, approved translation, rejected translation (if known),
  context, domain, language metadata, and tags.

### Benchmark references

`fixtures/translation_eval/approved_references.jsonl`

- Gold-reference fixture rows for evaluation:
  - `source_text`
  - `reference_translation`
  - `previous_context` / `next_context`
  - `source_lang` / `target_lang`
  - `domain` / `tags`

### SFT dataset (message format)

`artifacts/training/ja_en_subtitle_sft.jsonl`

Each line:

```json
{
  "messages": [
    {"role": "system", "content": "You translate Japanese subtitles into natural English subtitles."},
    {"role": "user", "content": "Context before: ...\nSource: ...\nContext after: ..."},
    {"role": "assistant", "content": "Approved English subtitle"}
  ],
  "metadata": {
    "source_lang": "ja",
    "target_lang": "en",
    "domain": "anime",
    "tags": ["name_error"],
    "language_pack": "ja_en"
  }
}
```

### Preference pairs

`artifacts/training/ja_en_preference_pairs.jsonl`

Each line:

```json
{
  "source_text": "...",
  "rejected_translation": "...",
  "chosen_translation": "...",
  "reason": "approved human correction preserves meaning better"
}
```

Rows without `bad_translation` are skipped and reported.

## Validation and safety

- Required fields: `source_text`, `approved_translation`, `source_lang`,
  `target_lang`.
- Incomplete rows are skipped and included in the export summary.
- Preference export also requires `bad_translation`.
- Safe to use for LoRA/SFT only after:
  - human review approval is complete,
  - private/sensitive text is removed per project policy,
  - domain/language metadata is present and correct,
  - skipped-row report is reviewed and cleaned.
