# Evaluation & Benchmarking

## Purpose
Benchmark mode provides quantitative comparison between multiple English subtitle generation paths for a single media asset.

## Candidate Sources
| ID Prefix | Path | Description |
|-----------|------|-------------|
| embedded_en | Demux EN subtitle track | Original authored English subtitles |
| en_audio_asr | EN audio → ASR | Direct English transcription |
| embedded_jp_mt | JP subs → MT (→ LLM) | Translation of Japanese subtitles |
| ja_audio_asr_mt | JP audio → ASR → MT (→ LLM) | Full speech translation chain |

LLM-polished variants append `_llm`.

## Metrics
| Metric | Source | Interpretation | Goal |
|--------|--------|----------------|------|
| WER | jiwer | Word error rate vs reference | Lower |
| BLEU | sacrebleu | n-gram translation quality | Higher |
| chrF | sacrebleu | Character-level F-score | Higher |

All metrics are computed corpus-level over aligned segments.

## Alignment
Temporal alignment pairs reference and candidate segments by maximum time overlap; many-to-one matches allowed. Fallback to midpoint proximity if no overlap.

## Reference Selection
Configured by `benchmark.reference_priority`. First matching candidate ID substring becomes reference. Fallback: first generated candidate.

Default priority:
1. embedded_en
2. en_audio_asr
3. ja_audio_asr_mt
4. embedded_jp_mt

## Pairwise Mode
Set `benchmark.compare_all_pairs: true` to compute all unique candidate pairs (O(N²)). Use for variance analysis; disable for performance.

## Output Structure (benchmark_results.json)
```json
{
  "video": "sample.mkv",
  "reference_id": "embedded_en_s10",
  "candidates": [ {"id": "embedded_en_s10", "segment_count": 120, "source": "embedded"}, ... ],
  "comparisons": [
    {
      "ref_id": "embedded_en_s10",
      "cand_id": "en_audio_asr_a0",
      "metrics": {"wer": 0.142, "bleu": 72.3, "chrf": 84.1},
      "num_segments": 120,
      "num_diffs": 34,
      "diffs": [ {"start": 12.5, "end": 14.0, "ref": "I can't believe it", "cand": "I cannot believe it"} ]
    }
  ]
}
```

`diffs` truncated to `benchmark.max_diffs_per_comparison`.

## Usage
```powershell
python main.py video.mkv --mode benchmark
```

Enable pairwise matrix:
```yaml
benchmark:
  compare_all_pairs: true
```

## Interpreting Metrics
- High BLEU + high chrF + low WER: candidate closely matches reference.
- High chrF but lower BLEU: stylistic or shorter segment differences; character overlap still strong.
- High WER but moderate chrF: many token substitutions (paraphrasing) but similar character distribution.

## Selecting Production Candidate
In absence of embedded EN subtitles, compare EN audio ASR vs JP→EN paths:
- Prefer lower WER if style differences acceptable.
- If LLM-polished MT significantly improves chrF/BLEU with acceptable WER, choose MT path.

## Reporting Enhancements
- HTML report rendered automatically alongside `benchmark_results.json` as `benchmark_report.html`.
- Self-contained single-file output (no external CSS/JS dependencies).
- Per-candidate scorecard table ranked by composite quality score.
- Diff viewer with per-segment reference vs. candidate highlighting.

## Candidate Scorecards

Each benchmark run produces a `scorecards` list in the output JSON.  One
scorecard is emitted per candidate and contains:

| Field | Description |
|---|---|
| `rank` | `"REF"` for the reference candidate; 1-based integer for others (1 = best) |
| `wer` / `bleu` / `chrf` | Metrics from the reference-vs-candidate comparison |
| `composite_score` | `0.5*(1-WER) + 0.25*(BLEU/100) + 0.25*(chrF/100)` |
| `is_reference` | Boolean |

## Result Persistence

When a registry is available (`artifacts.db_path` in config), every pairwise
comparison is stored as a `BenchmarkRunRecord` in the SQLite database.  Each
record carries the WER/BLEU/chrF snapshot plus the full metrics JSON blob.
The `run_id` field links all comparisons from the same session.

Query stored runs:

```python
from core.artifacts import ArtifactRegistry
reg = ArtifactRegistry("pipeline.db")
runs = reg.list_benchmark_runs(media_hash)
```

## Limitations
- Metrics not filtered for very short segments (BLEU may be 0).
- No OCR for bitmap subtitles (PGS/VobSub) yet.
- Reference selection string matching may need refinement for future source types.

## Extending Metrics
Add metrics in `compare_core.compute_metrics` and augment comparison dict with new fields. Ensure tests updated accordingly.
