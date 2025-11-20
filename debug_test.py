"""Quick debug test to see what's happening after ASR."""

from pathlib import Path
from config import Config, set_config
from asr import FasterWhisperASR

# Load config
config = Config()
set_config(config)

# Test with the extracted WAV file
audio_path = Path("temp") / "Kiki's Delivery Service (1989) {imdb-tt0097814} [Bluray-1080p Proper][EAC3 2.0][x265].wav"

if audio_path.exists():
    print(f"Found audio file: {audio_path}")
    print(f"File size: {audio_path.stat().st_size / 1024 / 1024:.1f} MB")
    
    print("\nRunning ASR...")
    asr = FasterWhisperASR(config)
    segments = asr.transcribe_audio_to_segments(str(audio_path))
    
    print(f"\nASR complete. Got {len(segments)} segments")
    print(f"Segments type: {type(segments)}")
    print(f"First segment type: {type(segments[0]) if segments else 'N/A'}")
    
    if segments:
        print(f"\nFirst segment:")
        print(f"  Start: {segments[0].start}")
        print(f"  End: {segments[0].end}")
        print(f"  Text JA: {segments[0].text_ja[:50]}")
        print(f"  Text EN raw: {segments[0].text_en_raw}")
        print(f"  Text EN final: {segments[0].text_en_final}")
    
    print("\nUnloading model...")
    # asr.unload_model()  # Disabled due to crash in destructor; investigate later
    print("(Skipped unload to avoid crash)")
    
    print("\nChecking if segments still accessible...")
    print(f"Segments length: {len(segments)}")
    print(f"Is list: {isinstance(segments, list)}")
    print(f"Bool value: {bool(segments)}")
    
    if not segments:
        print("ERROR: segments evaluated to False!")
    else:
        print("SUCCESS: segments evaluated to True")
    
else:
    print(f"Audio file not found: {audio_path}")
