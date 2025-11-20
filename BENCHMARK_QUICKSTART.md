# Benchmark Mode Quick Reference

## What It Does
Compares different English subtitle generation methods against an embedded reference subtitle track.

## Prerequisites
- Video with embedded EN subtitle (reference)
- At least one audio track (EN or JP)

## CLI Usage

```bash
# Run benchmark on a video
python main.py video.mkv --mode benchmark

# Benchmark without LLM polishing
python main.py video.mkv --mode benchmark --no-llm

# Check what tracks are available first
python main.py video.mkv --list-tracks
```

## Output
Creates `outbox/benchmark_results.json` with:
- Reference subtitle metadata
- Generated candidate metadata
- Comparison metrics (WER, BLEU, chrF)
- Text differences between candidates

## Comparison Candidates
1. **EN Audio ASR**: Direct English speech recognition (if EN audio exists)
2. **JP Audio ASR→MT→LLM**: Japanese audio → ASR → Translation → Polish (if JP audio exists)

## Metrics Explained

| Metric | Range | Better | Meaning |
|--------|-------|--------|---------|
| **WER** | 0.0 - 1.0+ | Lower | Word Error Rate (0.0 = perfect match) |
| **BLEU** | 0 - 100 | Higher | Translation quality (100 = perfect) |
| **chrF** | 0 - 100 | Higher | Character-level similarity (100 = perfect) |

## Example Output Summary
```
Benchmark Summary:
  en_audio_asr vs embedded_en_s2: WER=15.23%, BLEU=68.4, chrF=82.2
  ja_audio_asr_mt_llm vs embedded_en_s2: WER=32.41%, BLEU=45.2, chrF=65.8
```

## Common Issues

**"Benchmark requires embedded EN subtitle track"**
- Solution: Ensure video has text-based EN subtitle stream (check with `--list-tracks`)

**"No audio track found"**
- Solution: Video needs at least one audio track (EN or JP)

**Metrics show 0 or unexpected values**
- Short subtitle segments may produce zero BLEU scores (expected)
- WER and chrF are more reliable for short texts

## Testing
Run comprehensive tests:
```bash
python test_benchmark.py
```

## Next Steps
See `BENCHMARK_IMPLEMENTATION.md` for:
- Detailed architecture
- Future enhancement plans
- Technical implementation details
