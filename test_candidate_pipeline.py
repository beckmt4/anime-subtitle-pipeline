"""Test candidate-based pipeline (ASR → MT → LLM → SRT)."""
import os
import tempfile
from pathlib import Path
from config import Config
from models import Segment, SubtitleCandidate
from mt import translate_candidate_jp_to_en
from llm_polish import polish_candidate_with_llm, enforce_constraints_on_candidate
from srt_writer import write_candidate_srt


def test_candidate_pipeline():
    """Create synthetic Japanese candidate; translate; polish (if enabled); write SRT; validate."""
    
    # Build fake Japanese ASR candidate
    ja_segs = [
        Segment(start=0.0, end=2.0, text="こんにちは"),
        Segment(start=2.5, end=4.0, text="今日はいい天気ですね"),
    ]
    asr_candidate = SubtitleCandidate(
        id="asr_ja",
        language="ja",
        source="asr",
        origin_stream="audio:0",
        segments=ja_segs,
        meta={"model": "test"},
    )
    
    print(f"1. ASR candidate: {asr_candidate.id} ({asr_candidate.segment_count} segments)")
    for s in asr_candidate.segments:
        print(f"   [{s.start:.2f}-{s.end:.2f}] {s.text}")
    
    # Load config
    config = Config(config_path="config.yaml")
    
    # Step 2: Translate
    mt_candidate = translate_candidate_jp_to_en(asr_candidate, config)
    print(f"\n2. MT candidate: {mt_candidate.id} ({mt_candidate.segment_count} segments)")
    for s in mt_candidate.segments:
        print(f"   [{s.start:.2f}-{s.end:.2f}] {s.text}")
    
    # Step 3: Polish (if enabled)
    if config.llm_enabled:
        polished_candidate = polish_candidate_with_llm(mt_candidate, config)
        final_candidate = enforce_constraints_on_candidate(polished_candidate, config)
        print(f"\n3. Polished candidate: {final_candidate.id} ({final_candidate.segment_count} segments)")
        for s in final_candidate.segments:
            print(f"   [{s.start:.2f}-{s.end:.2f}] {s.text}")
    else:
        print("\n3. LLM polishing disabled; using MT candidate as final.")
        final_candidate = mt_candidate
    
    # Step 4: Write SRT
    with tempfile.TemporaryDirectory() as tmpdir:
        srt_path = Path(tmpdir) / "test_candidate.srt"
        result_path = write_candidate_srt(final_candidate, str(srt_path), config)
        print(f"\n4. SRT written to: {result_path}")
        with open(result_path, "r", encoding="utf-8") as f:
            srt_content = f.read()
        print("--- SRT Content ---")
        print(srt_content)
        print("--- End SRT ---")
    
    # Validation checks
    assert mt_candidate.language == "en", "MT candidate must be English"
    assert mt_candidate.segment_count == asr_candidate.segment_count, "MT segment count must match ASR"
    assert all(
        abs(s1.start - s2.start) < 0.01 and abs(s1.end - s2.end) < 0.01
        for s1, s2 in zip(asr_candidate.segments, mt_candidate.segments)
    ), "Timing must be preserved in MT candidate"
    assert final_candidate.segment_count > 0, "Final candidate must have at least one segment"
    # Accept any English-like text (LLM may polish "Hello" → "Hey there" etc.)
    assert any(word in srt_content.lower() for word in ["hello", "hey", "good", "nice", "day"]), "SRT must contain English text"
    
    print("\n✅ Candidate pipeline test PASSED: JA → EN MT → LLM (optional) → SRT verified")


if __name__ == "__main__":
    # Disable tracing for test if TRACING_ENABLED not set
    os.environ.setdefault("TRACING_ENABLED", "false")
    test_candidate_pipeline()
