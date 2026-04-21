# fixtures/

Stable test inputs and sample data for automated tests and benchmarking.

## Rules

- **Small.** Individual files should stay under 1 MB. Total fixtures should stay under 10 MB. If a fixture needs a large video file, document how to obtain it rather than committing it.
- **Deterministic.** A fixture produces the same output every time. Do not use fixtures that depend on network calls, model state, or timestamps.
- **Public domain or synthetic.** Do not commit copyrighted content. Use synthetically generated data or public domain sources. If a fixture comes from a real source, document the license.
- **Versioned intentionally.** Do not update fixture files silently. Changes to fixtures change test expectations. Note fixture changes explicitly in commit messages and PRs.

## Structure

```
fixtures/
  audio/          # Short WAV clips for ASR tests (synthetic or public domain)
  srt/            # Sample SRT files for parser and writer tests
  media/          # Minimal video containers (no real content)
  segments/       # JSON segment arrays for MT and polish tests
  benchmarks/     # Reference outputs for regression benchmarking
```

Create subdirectories as needed. Add a short comment at the top of complex fixture files explaining what they contain and why they have the shape they do.

## Naming

Use descriptive names that make the test scenario obvious:

```
fixtures/srt/valid_minimal.srt
fixtures/srt/overlapping_timestamps.srt
fixtures/segments/ja_900_segments.json     # the batch-size stress test case
fixtures/audio/silence_5sec_16khz.wav
```

## Relationship to tests

Fixtures are shared across test files. Import them by path from `fixtures/` rather than duplicating sample data inline in tests.
