"""Tests for generation strategy selection in orchestrator.run_generate.

Uses monkeypatching to avoid heavy I/O / model calls. Focuses purely on
decision logic given different MediaInfo configurations.
"""
import json
from pathlib import Path
from typing import List

import pytest

from models import SubtitleCandidate, Segment
from media_inspect import MediaInfo, AudioStream, SubtitleStream
from config import Config
from packs.language import LanguageRoutingHooks
import orchestrator as orch

# ---------------------------------------------------------------------------
# Helper candidate factories (lightweight)
# ---------------------------------------------------------------------------

def make_segments(tag: str) -> List[Segment]:
    return [Segment(start=0.0, end=1.0, text=f"{tag} one"), Segment(start=1.1, end=2.0, text=f"{tag} two")]


def stub_extract_subtitle_track(video, sub_index, language, output_dir=None):
    return SubtitleCandidate(
        id=f"embedded_{language}_s{sub_index}",
        language=language,
        source="embedded",
        origin_stream=f"sub:{sub_index}",
        segments=make_segments(f"sub-{language}"),
        meta={},
    )


def stub_extract_audio_with_ffmpeg(video_path: str, out_path: str, audio_order: int, **kwargs):
    Path(out_path).write_bytes(b"")  # create dummy file
    return out_path


class DummyASR:
    # Override per-test to control probe outcome: (language, probability)
    probe_result: tuple[str, float] = ("en", 0.95)
    # Set to an Exception instance to simulate a probe crash.
    probe_exception: Exception | None = None

    def __init__(self, cfg):
        pass

    def detect_language(self, audio_path: str) -> tuple[str, float]:
        if DummyASR.probe_exception is not None:
            raise DummyASR.probe_exception
        return DummyASR.probe_result

    def unload_model(self) -> None:
        pass

    def transcribe_audio_to_segments(self, path: str, language: str = "en"):
        segs = make_segments(f"asr-{language}")
        from models import SubtitleCandidate
        cand = SubtitleCandidate(
            id=f"asr_{language}",
            language=language,
            source="asr",
            origin_stream="audio:0",
            segments=segs,
            meta={},
        )
        return segs, cand


def stub_build_candidate_from_segments(segments, cfg, candidate_id, language, origin_stream):
    return SubtitleCandidate(
        id=candidate_id,
        language=language,
        source="asr" if language == "en" else "asr_mt",
        origin_stream=origin_stream,
        segments=segments,
        meta={},
    )


def stub_translate_candidate_jp_to_en(cand: SubtitleCandidate, cfg: Config):
    return SubtitleCandidate(
        id=cand.id.replace("embedded_ja", "embedded_jp_mt").replace("ja_audio_asr", "ja_audio_asr_mt"),
        language="en",
        source="embedded_mt" if cand.source == "embedded" else "asr_mt",
        origin_stream=cand.origin_stream,
        segments=[Segment(start=s.start, end=s.end, text=s.text + " EN") for s in cand.segments],
        meta={},
    )


def stub_translate_candidate_jp_to_en_workflow(
    cand: SubtitleCandidate,
    cfg: Config,
    engine=None,
    ja_candidate=None,
):
    translated = stub_translate_candidate_jp_to_en(cand, cfg)
    workflow = cfg.get("translation", "workflow", default="single_pass")
    translated.meta["translation_workflow"] = workflow
    if workflow == "literal_then_natural":
        translated.id = f"{translated.id}_natural"
        translated.source = "two_pass_llm"
    return translated


def stub_load_language_routing_hooks(source_language: str = "ja", target_language: str = "en"):
    return LanguageRoutingHooks(
        pack_id=f"{source_language}_{target_language}",
        source_language=source_language,
        target_language=target_language,
        lang_aliases={
            "ja": frozenset({"ja", "jpn", "jp", "ja-jp", "japanese"}),
            "en": frozenset({"en", "eng", "en-us", "en-gb", "english"}),
        },
        untagged_audio_fallback_source_language=source_language,
        translate_candidate=lambda cand, cfg, source_candidate=None: (
            orch.translate_candidate_jp_to_en_workflow(
                cand,
                cfg,
                ja_candidate=source_candidate or cand,
            )
        ),
    )


def stub_polish_candidate_with_llm(cand: SubtitleCandidate, cfg: Config, **kwargs):
    return SubtitleCandidate(
        id=cand.id + "_llm",
        language="en",
        source=cand.source + "_llm",
        origin_stream=cand.origin_stream,
        segments=[Segment(start=s.start, end=s.end, text=s.text.replace("one", "1")) for s in cand.segments],
        meta=cand.meta,
    )


def stub_polish_candidate_no_change(cand: SubtitleCandidate, cfg: Config, **kwargs):
    """Polish stub that returns identical text — simulates a no-op LLM."""
    return SubtitleCandidate(
        id=cand.id + "_llm",
        language="en",
        source=cand.source + "_llm",
        origin_stream=cand.origin_stream,
        segments=[Segment(start=s.start, end=s.end, text=s.text) for s in cand.segments],
        meta=cand.meta,
    )


def stub_polish_candidate_fallback(cand: SubtitleCandidate, cfg: Config, **kwargs):
    """Polish stub that simulates LLM unreachable (fallback pass-through)."""
    return SubtitleCandidate(
        id=cand.id + "_llm",
        language="en",
        source=cand.source + "_llm",
        origin_stream=cand.origin_stream,
        segments=[Segment(start=s.start, end=s.end, text=s.text) for s in cand.segments],
        meta={"fallback": True},
    )


def stub_enforce_constraints_on_candidate(cand: SubtitleCandidate, cfg: Config):
    return cand


def stub_write_candidate_srt(candidate: SubtitleCandidate, output_path: str, cfg: Config):
    p = Path(output_path)
    p.write_text("DUMMY SRT")
    return p


def _clean_qc_summary(*args, **kwargs):
    return {
        "parsed_ok": True,
        "cue_count": 2,
        "violations": [],
        "error_count": 0,
        "warning_count": 0,
        "pass_qc": True,
    }


# Install monkeypatches once
orch.extract_subtitle_track = stub_extract_subtitle_track
orch.extract_audio_with_ffmpeg = stub_extract_audio_with_ffmpeg
orch.FasterWhisperASR = DummyASR
orch.build_candidate_from_segments = stub_build_candidate_from_segments
orch.translate_candidate_jp_to_en = stub_translate_candidate_jp_to_en
orch.translate_candidate_jp_to_en_workflow = stub_translate_candidate_jp_to_en_workflow
orch.load_language_routing_hooks = stub_load_language_routing_hooks
orch.polish_candidate_with_llm = stub_polish_candidate_with_llm
orch.enforce_constraints_on_candidate = stub_enforce_constraints_on_candidate
orch.write_candidate_srt = stub_write_candidate_srt
orch.run_qc = _clean_qc_summary

# Ensure temp/outbox dirs exist
Path("temp").mkdir(exist_ok=True)
Path("outbox").mkdir(exist_ok=True)


def _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=False,
           en_sub_lang="en") -> MediaInfo:
    """Build a minimal MediaInfo for strategy tests.

    en_sub_lang: the language tag stored on the English subtitle stream (allows
    testing non-trivial tags like 'eng', 'en-US', etc.).
    """
    subs = []
    auds = []
    idx = 0
    if en_audio:
        auds.append(AudioStream(index=idx, codec="aac", language="en")); idx += 1
    if jp_audio:
        auds.append(AudioStream(index=idx, codec="aac", language="ja")); idx += 1
    sidx = 10
    if en_sub:
        subs.append(SubtitleStream(index=sidx, codec="subrip",
                                   language=en_sub_lang,
                                   raw_language=en_sub_lang)); sidx += 1
    if jp_sub:
        subs.append(SubtitleStream(index=sidx, codec="subrip", language="ja")); sidx += 1
    return MediaInfo(path=Path("dummy.mkv"), format_name="matroska", duration=120.0,
                     audio_streams=auds, subtitle_streams=subs)


def test_strategy_embedded_en():
    cfg = Config()
    media = _media(en_sub=True, en_audio=True, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_en", meta
    print("✓ embedded_en strategy chosen correctly")


def test_strategy_en_audio_when_no_en_sub_and_en_audio_preferred():
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_subtitles"] = False
    cfg._config["generate"]["prefer_audio_language"] = "en"
    media = _media(en_sub=False, en_audio=True, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "en_audio_asr", meta
    print("✓ en_audio_asr strategy chosen correctly")


def test_anime_domain_source_preferences_apply_in_inspect_mode():
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_subtitles"] = True
    cfg._config["generate"]["prefer_audio_language"] = "en"
    cfg._config["domain"] = {
        "pack": "anime",
        "anime": {
            "source_preferences": {
                "prefer_subtitles": False,
                "prefer_audio_language": "ja",
            }
        },
    }
    media = _media(en_sub=True, en_audio=True, jp_audio=True)
    meta = orch.run_generate(media, cfg, inspect_only=True)
    assert meta["domain_pack"] == "anime"
    assert meta["strategy"] == "ja_audio_asr_mt", meta


def test_packs_language_config_drives_language_routing_hook_resolution(monkeypatch):
    calls = []

    def fake_load_language_routing_hooks(source_language: str = "ja", target_language: str = "en"):
        calls.append((source_language, target_language))
        return LanguageRoutingHooks(
            pack_id="en_ja",
            source_language="ja",
            target_language="en",
            lang_aliases={
                "ja": frozenset({"ja", "jpn", "jp", "ja-jp", "japanese"}),
                "en": frozenset({"en", "eng", "en-us", "en-gb", "english"}),
            },
            untagged_audio_fallback_source_language="ja",
            translate_candidate=lambda cand, cfg, source_candidate=None: cand,
        )

    monkeypatch.setattr(orch, "load_language_routing_hooks", fake_load_language_routing_hooks)

    cfg = Config()
    cfg._config["packs"] = {"language": "en_ja"}
    media = _media(en_sub=True, en_audio=True, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg, inspect_only=True)

    assert calls == [("en", "ja")]
    assert meta["language_pack"] == "en_ja"


def test_anime_domain_pack_style_config_overrides_qc_defaults_and_injects_prompt_fn(monkeypatch):
    captured = {}

    def fake_polish_candidate_with_llm(cand: SubtitleCandidate, cfg: Config, **kwargs):
        captured["prompt_fn"] = kwargs.get("prompt_fn")
        return cand

    def fake_run_qc(*args, **kwargs):
        captured["qc_kwargs"] = kwargs
        return _clean_qc_summary()

    monkeypatch.setattr(orch, "polish_candidate_with_llm", fake_polish_candidate_with_llm)
    monkeypatch.setattr(orch, "run_qc", fake_run_qc)

    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_subtitles"] = True
    cfg._config["generate"]["use_llm_polish"] = True
    cfg._config["llm"]["max_chars_per_line"] = 55
    cfg._config["llm"]["max_lines"] = 3
    cfg._config["packs"] = {"language": "ja_en", "domain": "anime"}

    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)

    assert meta["strategy"] == "embedded_jp_mt"
    assert captured["qc_kwargs"]["max_line_chars"] == 42
    assert captured["qc_kwargs"]["max_lines"] == 2
    assert callable(captured["prompt_fn"])
    from packs.language.ja_en.prompts import get_system_prompt
    assert captured["prompt_fn"]("natural") == get_system_prompt("natural")


def test_jav_domain_requires_explicit_opt_in():
    from packs.domain.jav.privacy import ContentGateError

    cfg = Config()
    cfg._config.setdefault("domain", {})
    cfg._config["domain"].update({"pack": "jav", "adult_content_opt_in": False})
    media = _media(en_sub=True, en_audio=True, jp_audio=True)

    with pytest.raises(ContentGateError):
        orch.run_generate(media, cfg, inspect_only=True)


def test_jav_domain_redacts_inspect_report_and_uses_jav_preferences(monkeypatch):
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_subtitles"] = True
    cfg._config["generate"]["prefer_audio_language"] = "en"
    cfg._config["domain"] = {
        "pack": "jav",
        "adult_content_opt_in": True,
        "jav": {
            "source_preferences": {
                "prefer_subtitles": False,
                "prefer_audio_language": "ja",
            },
            "privacy": {
                "redact_logs": True,
                "redact_reports": True,
            },
        },
    }
    media = _media(en_sub=True, en_audio=True, jp_audio=True)
    media.path = Path("IPX-987 sample.mkv")

    monkeypatch.setattr(
        orch,
        "discover_sidecar_subtitles",
        lambda _path: [
            SubtitleCandidate(
                id="sidecar_en_ipx987",
                language="en",
                source="sidecar",
                origin_stream="sidecar:IPX-987.en.srt",
                segments=make_segments("sidecar-en"),
                meta={},
            )
        ],
    )

    meta = orch.run_generate(media, cfg, inspect_only=True)

    assert meta["domain_pack"] == "jav"
    assert meta["strategy"] == "ja_audio_asr_mt", meta
    assert meta["video"] == "<redacted>"
    assert meta["planned_output_srt"] == "<redacted>"
    assert meta["jav_media_id"] == "IPX-987"
    assert meta["review_mode"] == "adult"
    sources = meta["selection_report"]["sources_evaluated"]
    sidecar_entry = next(source for source in sources if source["source"] == "sidecar_en")
    assert sidecar_entry["stream"] == "sidecar:<redacted>"


def test_strategy_embedded_jp_mt():
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_jp_mt", meta
    assert meta["translation_qc"] is not None
    assert "qc_status" in meta["translation_qc"]
    print("✓ embedded_jp_mt strategy chosen correctly")


def test_strategy_ja_audio_asr_mt():
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "ja_audio_asr_mt", meta
    print("✓ ja_audio_asr_mt strategy chosen correctly")


def test_strategy_en_audio_fallback():
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_subtitles"] = False
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "en_audio_asr", meta
    print("✓ en_audio_asr fallback strategy chosen correctly")


# --- Regression: real-world language tag variants ---

def test_embedded_en_selected_with_eng_tag():
    """Regression (A Couple of Cuckoos): 'eng' ISO-639-2 tagged EN sub must win over generation."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=False, jp_audio=True,
                   en_sub_lang="eng")
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_en", (
        f"Expected embedded_en but got {meta['strategy']} — "
        "'eng' tag was not recognised as English"
    )
    print("✓ embedded_en selected for 'eng'-tagged subtitle (A Couple of Cuckoos regression)")


def test_embedded_en_selected_with_bcp47_en_us_tag():
    """Regression (Once Upon a Crime): 'en-US' BCP-47 tagged EN sub must win over generation."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=True, jp_audio=True,
                   en_sub_lang="en-US")
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_en", (
        f"Expected embedded_en but got {meta['strategy']} — "
        "'en-US' BCP-47 tag was not recognised as English"
    )
    print("✓ embedded_en selected for 'en-US'-tagged subtitle (Once Upon a Crime regression)")


def test_skip_embedded_en_forces_generation():
    """Preserve skip_embedded_en behavior: when set, pipeline must not use embedded EN."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=False, jp_audio=True)
    meta = orch.run_generate(media, cfg, skip_embedded_en=True)
    assert meta["strategy"] != "embedded_en", (
        f"Expected generation strategy but got {meta['strategy']} — "
        "skip_embedded_en=True should bypass embedded EN subtitles"
    )
    print("✓ skip_embedded_en=True correctly bypasses embedded EN subtitles")


# ---------------------------------------------------------------------------
# Language probe tests (issue #59)
# ---------------------------------------------------------------------------

def test_mislabeled_ja_audio_rerouted_via_probe():
    """EN-tagged audio that Whisper identifies as Japanese must route through JA ASR → MT."""
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    DummyASR.probe_result = ("ja", 0.97)
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        DummyASR.probe_result = ("en", 0.95)
    assert meta["strategy"] == "ja_audio_asr_mt", (
        f"Expected ja_audio_asr_mt but got {meta['strategy']} — "
        "mislabeled JA audio was not rerouted by language probe"
    )
    print("✓ Mislabeled JA audio (EN-tagged) correctly rerouted to ja_audio_asr_mt via probe")


def test_probe_confirmed_en_keeps_en_asr():
    """EN-tagged audio confirmed as English by probe stays on the EN ASR path."""
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    DummyASR.probe_result = ("en", 0.95)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "en_audio_asr", (
        f"Expected en_audio_asr but got {meta['strategy']} — "
        "confirmed EN audio should not be rerouted"
    )
    print("✓ Confirmed English audio stays on en_audio_asr path")


def test_probe_skipped_when_ja_audio_present():
    """Probe must not run when a proper JA-tagged audio track already exists."""
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=True)
    # If probe ran and returned "en", it would (incorrectly) keep EN audio.
    # The correct path is ja_audio_asr_mt regardless.
    DummyASR.probe_result = ("en", 0.99)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "ja_audio_asr_mt", (
        f"Expected ja_audio_asr_mt but got {meta['strategy']} — "
        "probe should be skipped when a JA-tagged track is present"
    )
    print("✓ Probe skipped when explicit JA audio track exists")


def test_probe_skipped_with_audio_track_override():
    """When --audio-track is specified, the probe must be bypassed entirely."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    # probe_result = "en" would keep EN ASR if probe ran; override forces JA path
    DummyASR.probe_result = ("en", 0.99)
    meta = orch.run_generate(media, cfg, audio_track_override=0)
    assert meta["strategy"] == "ja_audio_asr_mt", (
        f"Expected ja_audio_asr_mt but got {meta['strategy']} — "
        "--audio-track override should bypass probe and force JA path"
    )
    print("✓ Probe bypassed when --audio-track override is set")


def test_inconclusive_probe_falls_back_to_metadata():
    """Low-confidence probe result must not reroute — honour the metadata tag."""
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    DummyASR.probe_result = ("ja", 0.50)  # below 0.85 threshold
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        DummyASR.probe_result = ("en", 0.95)
    assert meta["strategy"] == "en_audio_asr", (
        f"Expected en_audio_asr but got {meta['strategy']} — "
        "inconclusive probe should not reroute"
    )
    print("✓ Inconclusive probe (low confidence) does not reroute; metadata tag honoured")


def test_probe_failure_adds_warning_to_en_asr_candidate():
    """When the probe crashes, the EN ASR candidate must carry a
    language_probe_failed source warning so its confidence is downgraded rather
    than the pipeline silently trusting the stream metadata tag."""
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    DummyASR.probe_exception = RuntimeError("'str' object has no attribute 'dtype'")
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        DummyASR.probe_exception = None

    assert meta["strategy"] == "en_audio_asr", (
        f"Expected en_audio_asr but got {meta['strategy']} — "
        "a failed probe should still route through EN ASR (metadata tag preserved)"
    )

    asr_quality = meta.get("asr_quality", {})
    source_warnings = asr_quality.get("source_warnings", [])
    warning_types = {w["type"] for w in source_warnings}
    assert "language_probe_failed" in warning_types, (
        f"Expected 'language_probe_failed' in asr_quality.source_warnings, "
        f"got: {warning_types}"
    )
    print("✓ Probe failure attaches language_probe_failed warning to EN ASR candidate")


# ---------------------------------------------------------------------------
# --source-language override tests (issue: add source-language override)
# ---------------------------------------------------------------------------

def test_source_language_ja_skips_probe_routes_en_tagged_audio_as_ja():
    """--source-language ja must bypass probe and treat EN-tagged audio as Japanese."""
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    # If probe ran, it would keep EN ASR; the override must skip it and force JA.
    DummyASR.probe_result = ("en", 0.99)
    meta = orch.run_generate(media, cfg, source_language="ja")
    assert meta["strategy"] == "ja_audio_asr_mt", (
        f"Expected ja_audio_asr_mt but got {meta['strategy']} — "
        "--source-language=ja should route EN-tagged audio through JA ASR"
    )
    print("✓ --source-language=ja routes EN-tagged audio through ja_audio_asr_mt (probe skipped)")


def test_source_language_en_routes_ja_tagged_audio_as_en():
    """--source-language en must treat JA-tagged audio as English and use EN ASR path."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=True)
    meta = orch.run_generate(media, cfg, source_language="en")
    assert meta["strategy"] == "en_audio_asr", (
        f"Expected en_audio_asr but got {meta['strategy']} — "
        "--source-language=en should route JA-tagged audio through EN ASR"
    )
    print("✓ --source-language=en routes JA-tagged audio through en_audio_asr")


def test_source_language_ja_mislabeled_metadata_no_probe():
    """When metadata says EN but user says --source-language ja, probe must not run."""
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)

    probe_called = []

    original_probe = orch._probe_audio_language

    def tracking_probe(*args, **kwargs):
        probe_called.append(args)
        return original_probe(*args, **kwargs)

    orch._probe_audio_language = tracking_probe
    try:
        meta = orch.run_generate(media, cfg, source_language="ja")
    finally:
        orch._probe_audio_language = original_probe

    assert meta["strategy"] == "ja_audio_asr_mt", (
        f"Expected ja_audio_asr_mt but got {meta['strategy']}"
    )
    assert len(probe_called) == 0, (
        f"Language probe must not be called when source_language is set, "
        f"but it was called {len(probe_called)} time(s)"
    )
    print("✓ Language probe not called when --source-language is set (mislabeled metadata case)")


def test_source_language_override_adds_source_warning():
    """A candidate produced with --source-language must carry a source_language_override warning."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    meta = orch.run_generate(media, cfg, source_language="ja")
    assert meta["strategy"] == "ja_audio_asr_mt", meta

    asr_quality = meta.get("asr_quality", {})
    source_warnings = asr_quality.get("source_warnings", [])
    warning_types = {w["type"] for w in source_warnings}
    assert "source_language_override" in warning_types, (
        f"Expected 'source_language_override' in asr_quality.source_warnings, "
        f"got: {warning_types}"
    )
    print("✓ source_language_override warning attached to ASR candidate")


def test_source_language_override_reported_in_selection_report():
    """--source-language must appear as an active override in the selection report."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    meta = orch.run_generate(media, cfg, source_language="ja")
    rpt = meta["selection_report"]
    assert any("source_language=ja" in o for o in rpt["overrides_active"]), (
        f"Expected 'source_language=ja' in overrides_active, got: {rpt['overrides_active']}"
    )
    print("✓ source_language=ja appears in selection_report overrides_active")


def test_source_language_auto_preserves_original_probe_behaviour():
    """--source-language auto (default) must still run the probe for mislabeled EN audio."""
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    DummyASR.probe_result = ("ja", 0.97)
    try:
        meta = orch.run_generate(media, cfg, source_language="auto")
    finally:
        DummyASR.probe_result = ("en", 0.95)
    assert meta["strategy"] == "ja_audio_asr_mt", (
        f"Expected ja_audio_asr_mt (probe detected JA) but got {meta['strategy']} — "
        "source_language=auto should preserve probe-based rerouting"
    )
    print("✓ source_language=auto preserves existing probe-based rerouting")


def test_source_language_inspect_only_uses_override():
    """inspect-only mode must apply the source_language override when planning strategy."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("inspect_only must not run ASR or file I/O")

    original_asr = orch.FasterWhisperASR
    original_ffmpeg = orch.extract_audio_with_ffmpeg
    orch.FasterWhisperASR = forbidden
    orch.extract_audio_with_ffmpeg = forbidden
    try:
        meta = orch.run_generate(media, cfg, inspect_only=True, source_language="ja")
    finally:
        orch.FasterWhisperASR = original_asr
        orch.extract_audio_with_ffmpeg = original_ffmpeg

    assert meta["inspect_only"] is True
    assert meta["strategy"] == "ja_audio_asr_mt", (
        f"Expected ja_audio_asr_mt but got {meta['strategy']} — "
        "inspect-only should plan ja_audio_asr_mt when source_language=ja"
    )
    print("✓ inspect-only correctly plans ja_audio_asr_mt when source_language=ja")


def test_source_language_untagged_audio_respects_override():
    """--source-language ja on a file with no language-tagged audio must also route JA."""
    from media_inspect import AudioStream
    cfg = Config()
    untagged_media = MediaInfo(
        path=Path("untagged.mkv"),
        format_name="matroska",
        duration=120.0,
        audio_streams=[AudioStream(index=0, codec="aac", language=None)],
        subtitle_streams=[],
    )
    meta = orch.run_generate(untagged_media, cfg, source_language="ja")
    assert meta["strategy"] == "ja_audio_asr_mt", (
        f"Expected ja_audio_asr_mt but got {meta['strategy']} — "
        "source_language=ja should route untagged audio through JA ASR"
    )
    print("✓ --source-language=ja routes untagged audio through ja_audio_asr_mt")


def run_all_tests():
    test_strategy_embedded_en()
    test_strategy_en_audio_when_no_en_sub_and_en_audio_preferred()
    test_strategy_embedded_jp_mt()
    test_strategy_ja_audio_asr_mt()
    test_strategy_en_audio_fallback()
    test_embedded_en_selected_with_eng_tag()
    test_embedded_en_selected_with_bcp47_en_us_tag()
    test_skip_embedded_en_forces_generation()
    test_compare_candidates_changed()
    test_compare_candidates_no_change()
    test_compare_candidates_fallback()
    test_polish_status_changed_in_metadata()
    test_polish_status_no_change_in_metadata()
    test_polish_status_fallback_in_metadata()
    test_no_polish_status_for_non_mt_strategies()
    # Language probe tests (issue #59)
    test_mislabeled_ja_audio_rerouted_via_probe()
    test_probe_confirmed_en_keeps_en_asr()
    test_probe_skipped_when_ja_audio_present()
    test_probe_skipped_with_audio_track_override()
    test_inconclusive_probe_falls_back_to_metadata()
    test_probe_failure_adds_warning_to_en_asr_candidate()
    # --source-language override tests
    test_source_language_ja_skips_probe_routes_en_tagged_audio_as_ja()
    test_source_language_en_routes_ja_tagged_audio_as_en()
    test_source_language_ja_mislabeled_metadata_no_probe()
    test_source_language_override_adds_source_warning()
    test_source_language_override_reported_in_selection_report()
    test_source_language_auto_preserves_original_probe_behaviour()
    test_source_language_inspect_only_uses_override()
    test_source_language_untagged_audio_respects_override()
    # Explainable selection report tests (issue #52 / #20)
    test_selection_report_present_in_metadata()
    test_selection_report_embedded_en_high_confidence()
    test_selection_report_alternatives_listed_for_embedded_en()
    test_selection_report_not_available_sources_shown()
    test_selection_report_mt_strategy_low_confidence_review_recommended()
    test_selection_report_embedded_jp_mt_low_confidence_review_recommended()
    test_selection_report_skip_embedded_en_override()
    test_selection_report_audio_track_override()
    test_selection_report_untagged_audio_fallback()
    test_selection_report_probe_reroute_reflected()
    test_selection_report_rationale_is_nonempty_string()
    # Candidate scoring tests
    test_score_candidate_structure()
    test_score_candidate_embedded_en_high_score()
    test_score_candidate_untagged_audio_low_score()
    test_score_candidate_ordering()
    test_score_candidate_qc_penalises_errors()
    test_score_candidate_no_qc_uses_neutral()
    test_score_candidate_segment_yield_partial()
    test_score_candidate_in_run_generate_metadata()
    test_score_candidate_grade_thresholds()
    print("\n✅ All orchestrator strategy tests PASSED")


# ---------------------------------------------------------------------------
# score_candidate unit tests
# ---------------------------------------------------------------------------

def _make_candidate(candidate_id: str = "test", segment_count: int = 5) -> "SubtitleCandidate":
    return SubtitleCandidate(
        id=candidate_id,
        language="en",
        source="embedded",
        origin_stream="sub:0",
        segments=make_segments("test")[:segment_count] if segment_count <= 2
        else [Segment(float(i), float(i + 1), f"seg {i}") for i in range(segment_count)],
        meta={},
    )


def _make_qc_summary(cue_count: int, error_count: int = 0, warning_count: int = 0) -> dict:
    return {
        "parsed_ok": True,
        "cue_count": cue_count,
        "violations": [],
        "error_count": error_count,
        "warning_count": warning_count,
        "pass_qc": error_count == 0,
    }


def test_score_candidate_structure():
    """score_candidate must return the expected keys and types."""
    cand = _make_candidate(segment_count=5)
    result = orch.score_candidate("embedded_en", cand, _make_qc_summary(5))
    assert "total_score" in result, result
    assert "grade" in result, result
    assert "factors" in result, result
    assert isinstance(result["total_score"], (int, float)), result
    assert isinstance(result["grade"], str), result
    assert isinstance(result["factors"], list), result
    for f in result["factors"]:
        for key in ("name", "description", "raw_value", "max_contribution", "contribution"):
            assert key in f, f"factor missing key '{key}': {f}"
    print("✓ score_candidate: structure correct")


def test_score_candidate_embedded_en_high_score():
    """embedded_en with clean QC and sufficient segments must achieve grade A."""
    cand = _make_candidate(segment_count=10)
    result = orch.score_candidate("embedded_en", cand, _make_qc_summary(10))
    assert result["total_score"] >= 80, result
    assert result["grade"] == "A", result
    print(f"✓ embedded_en scores {result['total_score']:.1f} (grade {result['grade']})")


def test_score_candidate_untagged_audio_low_score():
    """untagged_audio_asr_mt with low segment count must score below embedded_en."""
    embedded = orch.score_candidate("embedded_en", _make_candidate(10), _make_qc_summary(10))
    untagged = orch.score_candidate("untagged_audio_asr_mt", _make_candidate(2), _make_qc_summary(2))
    assert untagged["total_score"] < embedded["total_score"], (
        f"Expected untagged ({untagged['total_score']}) < embedded_en ({embedded['total_score']})"
    )
    print(
        f"✓ untagged_audio_asr_mt ({untagged['total_score']}) "
        f"< embedded_en ({embedded['total_score']})"
    )


def test_score_candidate_ordering():
    """Higher-quality strategies must score higher than lower-quality ones (equal QC/segments)."""
    qc = _make_qc_summary(10)
    cand = _make_candidate(segment_count=10)
    scores = {
        s: orch.score_candidate(s, cand, qc)["total_score"]
        for s in ("embedded_en", "en_audio_asr", "embedded_jp_mt",
                  "ja_audio_asr_mt", "untagged_audio_asr_mt")
    }
    assert scores["embedded_en"] > scores["en_audio_asr"], scores
    assert scores["en_audio_asr"] > scores["embedded_jp_mt"], scores
    assert scores["embedded_jp_mt"] > scores["ja_audio_asr_mt"], scores
    assert scores["ja_audio_asr_mt"] > scores["untagged_audio_asr_mt"], scores
    print("✓ Strategy score ordering correct:", {k: round(v, 1) for k, v in scores.items()})


def test_score_candidate_qc_penalises_errors():
    """QC errors must reduce the qc_pass_rate factor contribution."""
    cand = _make_candidate(segment_count=10)
    clean_score = orch.score_candidate("embedded_jp_mt", cand, _make_qc_summary(10, error_count=0))
    dirty_score = orch.score_candidate("embedded_jp_mt", cand, _make_qc_summary(10, error_count=5))
    assert clean_score["total_score"] > dirty_score["total_score"], (
        f"Clean ({clean_score['total_score']}) should exceed dirty ({dirty_score['total_score']})"
    )
    clean_qc = next(f for f in clean_score["factors"] if f["name"] == "qc_pass_rate")
    dirty_qc = next(f for f in dirty_score["factors"] if f["name"] == "qc_pass_rate")
    assert clean_qc["contribution"] > dirty_qc["contribution"], (
        "qc_pass_rate contribution should be lower when errors present"
    )
    print(
        f"✓ QC errors reduce score: clean={clean_score['total_score']:.1f} "
        f"vs dirty={dirty_score['total_score']:.1f}"
    )


def test_score_candidate_no_qc_uses_neutral():
    """When qc_summary is None, the qc_pass_rate factor must use the neutral value."""
    cand = _make_candidate(segment_count=10)
    result = orch.score_candidate("embedded_en", cand, None)
    qc_factor = next(f for f in result["factors"] if f["name"] == "qc_pass_rate")
    assert qc_factor["raw_value"] is None, qc_factor
    # Neutral = 0.5 × max (10 pts)
    assert qc_factor["contribution"] == 10.0, qc_factor
    print("✓ No QC summary: neutral half-score applied to qc_pass_rate")


def test_score_candidate_segment_yield_partial():
    """Candidates with fewer than 5 segments must receive a partial segment_yield score."""
    cand_few = _make_candidate(segment_count=2)
    cand_full = _make_candidate(segment_count=5)
    qc = _make_qc_summary(5)
    score_few = orch.score_candidate("embedded_en", cand_few, qc)
    score_full = orch.score_candidate("embedded_en", cand_full, qc)
    yield_few = next(f for f in score_few["factors"] if f["name"] == "segment_yield")
    yield_full = next(f for f in score_full["factors"] if f["name"] == "segment_yield")
    assert yield_few["contribution"] < yield_full["contribution"], (
        f"Partial yield ({yield_few['contribution']}) should be < full yield ({yield_full['contribution']})"
    )
    assert yield_full["contribution"] == yield_full["max_contribution"], yield_full
    print(
        f"✓ Partial segment yield: 2 segs → {yield_few['contribution']} pts, "
        f"5 segs → {yield_full['contribution']} pts"
    )


def test_score_candidate_in_run_generate_metadata():
    """run_generate must include 'candidate_score' with correct structure in its return value."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=False, jp_audio=False)
    meta = orch.run_generate(media, cfg)
    assert "candidate_score" in meta, "candidate_score missing from metadata"
    cs = meta["candidate_score"]
    assert "total_score" in cs, cs
    assert "grade" in cs, cs
    assert "factors" in cs, cs
    assert isinstance(cs["total_score"], (int, float)), cs
    factor_names = {f["name"] for f in cs["factors"]}
    assert "strategy_base" in factor_names, factor_names
    assert "qc_pass_rate" in factor_names, factor_names
    assert "segment_yield" in factor_names, factor_names
    print(
        f"✓ candidate_score in run_generate metadata: "
        f"score={cs['total_score']:.1f}, grade={cs['grade']}"
    )


def test_run_generate_metadata_includes_asr_quality_summary(monkeypatch):
    """Generate metadata must expose ASR low-confidence counts."""

    def build_candidate_with_asr_warning(segments, cfg, candidate_id, language, origin_stream):
        warning = {
            "type": "low_average_log_probability",
            "severity": "warning",
            "detail": "avg_logprob -2.00 < -1.00",
        }
        return SubtitleCandidate(
            id=candidate_id,
            language=language,
            source="asr",
            origin_stream=origin_stream,
            segments=[
                Segment(s.start, s.end, s.text, meta={"asr": {"low_confidence": True, "warnings": [warning]}})
                for s in segments
            ],
            meta={
                "asr_quality": {
                    "status": "warn",
                    "segment_count": len(segments),
                    "low_confidence_segment_count": len(segments),
                    "low_confidence_ratio": 1.0,
                    "warning_count": len(segments),
                    "summary_warnings": [],
                },
                "asr_quality_status": "warn",
                "asr_low_confidence_segment_count": len(segments),
            },
        )

    monkeypatch.setattr(orch, "build_candidate_from_segments", build_candidate_with_asr_warning)
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_audio_language"] = "en"
    media = _media(en_audio=True)

    meta = orch.run_generate(media, cfg)

    assert meta["strategy"] == "en_audio_asr"
    assert meta["asr_low_confidence_segment_count"] == 2
    assert meta["asr_quality"]["status"] == "warn"


def test_score_candidate_grade_thresholds():
    """Grade must be correctly assigned based on total_score thresholds."""
    # Force specific total scores via untagged strategy + controlled QC
    # untagged_audio_asr_mt base = 15 → with 1 segment and 100% errors total ≈ 3
    cand_tiny = _make_candidate(segment_count=1)
    qc_all_errors = _make_qc_summary(cue_count=1, error_count=1)
    result_f = orch.score_candidate("untagged_audio_asr_mt", cand_tiny, qc_all_errors)
    assert result_f["grade"] == "F", f"Expected F but got {result_f['grade']} ({result_f['total_score']})"

    # embedded_en + perfect QC + 10 segs → should be A
    cand_good = _make_candidate(segment_count=10)
    qc_clean = _make_qc_summary(cue_count=10, error_count=0)
    result_a = orch.score_candidate("embedded_en", cand_good, qc_clean)
    assert result_a["grade"] == "A", f"Expected A but got {result_a['grade']} ({result_a['total_score']})"

    print(
        f"✓ Grade thresholds: F at {result_f['total_score']:.1f}, "
        f"A at {result_a['total_score']:.1f}"
    )


def test_score_candidate_includes_translation_qc_summary_fields():
    """candidate_score should carry translation QC status + warning/fail counts."""
    cand = _make_candidate(segment_count=10)
    qc_clean = _make_qc_summary(cue_count=10, error_count=0)
    translation_qc = {
        "qc_status": "warn",
        "summary": {"warning_count": 2, "fail_count": 0, "review_required_segments": 1},
    }
    result = orch.score_candidate(
        "embedded_jp_mt",
        cand,
        qc_clean,
        translation_qc_summary=translation_qc,
    )
    assert result["translation_qc_status"] == "warn", result
    assert result["translation_qc_warning_count"] == 2, result
    assert result["translation_qc_fail_count"] == 0, result
    factor_names = {f["name"] for f in result["factors"]}
    assert "translation_qc_status" in factor_names, result


# ---------------------------------------------------------------------------
# _compare_candidates unit tests
# ---------------------------------------------------------------------------

def test_compare_candidates_changed():
    raw = SubtitleCandidate(
        id="raw", language="en", source="mt", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello world"), Segment(1.0, 2.0, "Goodbye")],
        meta={},
    )
    polished = SubtitleCandidate(
        id="raw_llm", language="en", source="mt_llm", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello, world!"), Segment(1.0, 2.0, "Goodbye")],
        meta={},
    )
    result = orch._compare_candidates(raw, polished)
    assert result["polish_status"] == "changed", result
    assert result["segments_changed"] == 1
    assert result["segments_unchanged"] == 1
    print("✓ _compare_candidates: changed status correct")


def test_compare_candidates_no_change():
    raw = SubtitleCandidate(
        id="raw", language="en", source="mt", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello world"), Segment(1.0, 2.0, "Goodbye")],
        meta={},
    )
    polished = SubtitleCandidate(
        id="raw_llm", language="en", source="mt_llm", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello world"), Segment(1.0, 2.0, "Goodbye")],
        meta={},
    )
    result = orch._compare_candidates(raw, polished)
    assert result["polish_status"] == "no_change", result
    assert result["segments_changed"] == 0
    assert result["segments_unchanged"] == 2
    print("✓ _compare_candidates: no_change status correct")


def test_compare_candidates_fallback():
    raw = SubtitleCandidate(
        id="raw", language="en", source="mt", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello world"), Segment(1.0, 2.0, "Goodbye")],
        meta={},
    )
    polished = SubtitleCandidate(
        id="raw_llm", language="en", source="mt_llm", origin_stream="sub:0",
        segments=[Segment(0.0, 1.0, "Hello world"), Segment(1.0, 2.0, "Goodbye")],
        meta={"fallback": True},
    )
    result = orch._compare_candidates(raw, polished)
    assert result["polish_status"] == "fallback", result
    assert result["segments_changed"] == 0
    assert result["segments_unchanged"] == 2
    print("✓ _compare_candidates: fallback status correct")


# ---------------------------------------------------------------------------
# run_generate polish_status metadata tests
# ---------------------------------------------------------------------------

def test_polish_status_changed_in_metadata():
    """When LLM polish changes segments, metadata should report polish_status=changed."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=False)
    # Default stub (stub_polish_candidate_with_llm) changes text containing "one"
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_jp_mt"
    assert "polish_status" in meta, meta
    assert meta["polish_status"] == "changed", meta
    assert "segments_changed" in meta
    assert "segments_unchanged" in meta
    print("✓ polish_status=changed present in metadata for changed polish")


def test_polish_status_no_change_in_metadata():
    """When LLM polish leaves all segments identical, metadata reports no_change."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=False)
    original_stub = orch.polish_candidate_with_llm
    orch.polish_candidate_with_llm = stub_polish_candidate_no_change
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        orch.polish_candidate_with_llm = original_stub
    assert meta["strategy"] == "embedded_jp_mt"
    assert meta["polish_status"] == "no_change", meta
    assert meta["segments_changed"] == 0
    assert meta["segments_unchanged"] > 0
    print("✓ polish_status=no_change present in metadata for identical polish")


def test_polish_status_fallback_in_metadata():
    """When LLM is unreachable (fallback), metadata reports polish_status=fallback."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=True)
    original_stub = orch.polish_candidate_with_llm
    orch.polish_candidate_with_llm = stub_polish_candidate_fallback
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        orch.polish_candidate_with_llm = original_stub
    assert meta["strategy"] == "ja_audio_asr_mt"
    assert meta["polish_status"] == "fallback", meta
    print("✓ polish_status=fallback present in metadata for LLM fallback")


def test_no_polish_status_for_non_mt_strategies():
    """Strategies that don't run LLM polish should omit polish_status from metadata."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=False, jp_audio=False)
    meta = orch.run_generate(media, cfg)
    assert meta["strategy"] == "embedded_en"
    assert "polish_status" not in meta, meta
    print("✓ polish_status absent for strategies that skip LLM polish")


def test_two_pass_workflow_skips_generic_post_mt_polish_by_default():
    """literal_then_natural should not be polished again by generic post-MT LLM pass."""
    cfg = Config()
    cfg._config.setdefault("translation", {})
    cfg._config["translation"]["workflow"] = "literal_then_natural"
    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=False)

    original_stub = orch.polish_candidate_with_llm

    def forbidden(*args, **kwargs):
        raise AssertionError("Generic LLM polish must be skipped for literal_then_natural workflow")

    orch.polish_candidate_with_llm = forbidden
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        orch.polish_candidate_with_llm = original_stub

    assert meta["strategy"] == "embedded_jp_mt"
    assert meta.get("translation_workflow") == "literal_then_natural", meta
    assert "polish_status" not in meta, meta


def test_two_pass_workflow_can_opt_in_generic_post_mt_polish():
    """allow_post_two_pass_llm should enable an explicit second polishing pass."""
    cfg = Config()
    cfg._config.setdefault("translation", {})
    cfg._config["translation"]["workflow"] = "literal_then_natural"
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["allow_post_two_pass_llm"] = True
    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=False)

    meta = orch.run_generate(media, cfg)

    assert meta["strategy"] == "embedded_jp_mt"
    assert meta.get("translation_workflow") == "literal_then_natural", meta
    assert meta.get("polish_status") == "changed", meta


# ---------------------------------------------------------------------------
# Explainable source-selection report tests (issue #52 / #20)
# ---------------------------------------------------------------------------

def test_selection_report_present_in_metadata():
    """run_generate must always include a 'selection_report' key in its return value."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=False, jp_audio=False)
    meta = orch.run_generate(media, cfg)
    assert "selection_report" in meta, "selection_report missing from metadata"
    rpt = meta["selection_report"]
    for key in ("selected_source", "confidence_tier", "rationale", "sources_evaluated",
                "overrides_active", "review_recommended"):
        assert key in rpt, f"selection_report missing key '{key}'"
    print("✓ selection_report present with all required keys")


def test_selection_report_embedded_en_high_confidence():
    """embedded_en strategy must produce confidence_tier=high and no review recommendation."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=True, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    rpt = meta["selection_report"]
    assert rpt["selected_source"] == "embedded_en", rpt
    assert rpt["confidence_tier"] == "high", rpt
    assert rpt["review_recommended"] is False, rpt
    assert rpt["review_reason"] is None, rpt
    print("✓ embedded_en: high confidence, no review recommended")


def test_selection_report_alternatives_listed_for_embedded_en():
    """When embedded_en wins, all other available sources must appear as 'skipped'."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=True, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    rpt = meta["selection_report"]
    statuses = {s["source"]: s["status"] for s in rpt["sources_evaluated"]}
    assert statuses["embedded_en"] == "selected", statuses
    assert statuses["en_audio_asr"] == "skipped", statuses
    assert statuses["embedded_jp_mt"] == "skipped", statuses
    assert statuses["ja_audio_asr_mt"] == "skipped", statuses
    print("✓ All alternatives shown as skipped when embedded_en is selected")


def test_selection_report_not_available_sources_shown():
    """Sources absent from the container must appear with status 'not_available'."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    rpt = meta["selection_report"]
    statuses = {s["source"]: s["status"] for s in rpt["sources_evaluated"]}
    assert statuses["embedded_en"] == "not_available", statuses
    assert statuses["en_audio_asr"] == "not_available", statuses
    assert statuses["embedded_jp_mt"] == "not_available", statuses
    assert statuses["ja_audio_asr_mt"] == "selected", statuses
    print("✓ Not-available sources correctly flagged in selection report")


def test_selection_report_mt_strategy_low_confidence_review_recommended():
    """ja_audio_asr_mt must be flagged as low confidence and require review."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    rpt = meta["selection_report"]
    assert rpt["selected_source"] == "ja_audio_asr_mt", rpt
    assert rpt["confidence_tier"] == "low", rpt
    assert rpt["review_recommended"] is True, rpt
    assert rpt["review_reason"] is not None, rpt
    print("✓ ja_audio_asr_mt: low confidence, review recommended")


def test_selection_report_embedded_jp_mt_low_confidence_review_recommended():
    """embedded_jp_mt must be flagged as low confidence and require review."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=False)
    meta = orch.run_generate(media, cfg)
    rpt = meta["selection_report"]
    assert rpt["selected_source"] == "embedded_jp_mt", rpt
    assert rpt["confidence_tier"] == "low", rpt
    assert rpt["review_recommended"] is True, rpt
    print("✓ embedded_jp_mt: low confidence, review recommended")


def test_selection_report_skip_embedded_en_override():
    """When skip_embedded_en is True, the report must list 'skip_embedded_en' as an override
    and show embedded_en as 'skipped' (not 'not_available')."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=False, jp_sub=False, jp_audio=True)
    meta = orch.run_generate(media, cfg, skip_embedded_en=True)
    rpt = meta["selection_report"]
    assert "skip_embedded_en" in rpt["overrides_active"], rpt
    statuses = {s["source"]: s["status"] for s in rpt["sources_evaluated"]}
    assert statuses["embedded_en"] == "skipped", statuses
    # The stream reference should still be present since it was detected
    en_entry = next(
        (s for s in rpt["sources_evaluated"] if s["source"] == "embedded_en"), None
    )
    assert en_entry is not None, "embedded_en entry missing from sources_evaluated"
    assert en_entry["detected"] is True, en_entry
    print("✓ skip_embedded_en override correctly reflected in selection report")


def test_selection_report_audio_track_override():
    """When audio_track_override is set, the report must note the override and show
    all other sources as bypassed."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=True, jp_sub=True, jp_audio=False)
    meta = orch.run_generate(media, cfg, audio_track_override=0)
    rpt = meta["selection_report"]
    assert any("audio_track_override" in o for o in rpt["overrides_active"]), rpt
    assert rpt["selected_source"] == "ja_audio_asr_mt", rpt
    statuses = {s["source"]: s["status"] for s in rpt["sources_evaluated"]}
    assert statuses["embedded_en"] == "skipped", statuses
    assert statuses["en_audio_asr"] == "skipped", statuses
    assert statuses["embedded_jp_mt"] == "skipped", statuses
    assert statuses["ja_audio_asr_mt"] == "selected", statuses
    print("✓ audio_track_override correctly reflected in selection report")


def test_selection_report_untagged_audio_fallback():
    """When only an untagged audio stream is present and the language probe is
    inconclusive, the report must record the untagged_audio_asr_mt fallback with
    very_low confidence."""
    from media_inspect import AudioStream
    untagged_audio_stream = AudioStream(index=0, codec="aac", language=None)
    media = MediaInfo(
        path=Path("untagged.mkv"),
        format_name="matroska",
        duration=120.0,
        audio_streams=[untagged_audio_stream],
        subtitle_streams=[],
    )
    cfg = Config()
    # Simulate an inconclusive language probe (confidence below threshold)
    # so the pipeline falls through to the untagged_audio_asr_mt path.
    DummyASR.probe_result = ("und", 0.3)
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        DummyASR.probe_result = ("en", 0.95)
    assert meta["strategy"] == "untagged_audio_asr_mt", meta
    rpt = meta["selection_report"]
    assert rpt["selected_source"] == "untagged_audio_asr_mt", rpt
    assert rpt["confidence_tier"] == "very_low", rpt
    assert rpt["review_recommended"] is True, rpt
    untagged_entry = next(
        (s for s in rpt["sources_evaluated"] if s["source"] == "untagged_audio_asr_mt"),
        None,
    )
    assert untagged_entry is not None, "untagged_audio_asr_mt missing from sources_evaluated"
    assert untagged_entry["status"] == "selected", untagged_entry
    routing = rpt["language_routing"]
    assert routing["language_pack"] == "ja_en", routing
    assert routing["untagged_audio_fallback_source_language"] == "ja", routing
    assert "language-pack fallback policy" in untagged_entry["reason"], untagged_entry
    print("✓ untagged_audio_asr_mt fallback: very_low confidence, review recommended")


def test_generate_metadata_includes_language_pack_routing_context():
    cfg = Config()
    media = _media(en_sub=True, en_audio=True, jp_sub=True, jp_audio=True)
    meta = orch.run_generate(media, cfg)
    assert meta["language_pack"] == "ja_en", meta
    assert meta["translation_source_language"] == "ja", meta
    assert meta["translation_target_language"] == "en", meta
    routing = meta["selection_report"]["language_routing"]
    assert routing["language_pack"] == "ja_en", routing
    assert routing["translation_source_language"] == "ja", routing
    assert routing["translation_target_language"] == "en", routing


def test_selection_report_probe_reroute_reflected():
    """When a language probe reroutes EN-tagged audio to ja_audio_asr_mt, the report
    must explain this in the rationale and show en_audio_asr as 'skipped'."""
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["prefer_audio_language"] = "auto"
    media = _media(en_sub=False, en_audio=True, jp_sub=False, jp_audio=False)
    DummyASR.probe_result = ("ja", 0.97)
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        DummyASR.probe_result = ("en", 0.95)
    rpt = meta["selection_report"]
    assert rpt["selected_source"] == "ja_audio_asr_mt", rpt
    statuses = {s["source"]: s["status"] for s in rpt["sources_evaluated"]}
    assert statuses["en_audio_asr"] == "skipped", statuses
    assert statuses["ja_audio_asr_mt"] == "selected", statuses
    # Rationale or the ja_audio entry's reason should mention the probe
    ja_entry = next(
        (s for s in rpt["sources_evaluated"] if s["source"] == "ja_audio_asr_mt"), None
    )
    assert ja_entry is not None, "ja_audio_asr_mt entry missing from sources_evaluated"
    assert "probe" in ja_entry["reason"].lower() or "probe" in rpt["rationale"].lower(), (
        "language probe reroute not mentioned in selection report"
    )
    print("✓ Language probe reroute correctly described in selection report")


def test_selection_report_rationale_is_nonempty_string():
    """The 'rationale' field must always be a non-empty string for every strategy."""
    cfg = Config()
    cases = [
        (_media(en_sub=True),                 "embedded_en"),
        (_media(en_audio=True, jp_audio=True), "ja_audio_asr_mt"),
        (_media(jp_sub=True),                  "embedded_jp_mt"),
        (_media(jp_audio=True),                "ja_audio_asr_mt"),
    ]
    for media, expected_strategy in cases:
        meta = orch.run_generate(media, cfg)
        rpt = meta["selection_report"]
        assert rpt["selected_source"] == expected_strategy, (
            f"Expected strategy {expected_strategy!r} but got {rpt['selected_source']!r}"
        )
        assert isinstance(rpt["rationale"], str) and rpt["rationale"], (
            f"Empty rationale for strategy {rpt['selected_source']!r}"
        )
    print("✓ Rationale is a non-empty string for all strategies")


def test_generate_no_usable_source_error_case():
    """No subtitles or audio sources should fail clearly."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=False)

    try:
        orch.run_generate(media, cfg)
    except RuntimeError as exc:
        assert "No usable source found" in str(exc)
    else:
        raise AssertionError("Expected run_generate to reject media with no usable sources")


# ---------------------------------------------------------------------------
# Generate inspect-only tests (issue #53)
# ---------------------------------------------------------------------------

def test_inspect_only_embedded_en_skips_execution_calls():
    """Inspect-only should plan embedded EN without extracting or writing subtitles."""
    cfg = Config()
    media = _media(en_sub=True, en_audio=True, jp_sub=True, jp_audio=True)
    original_extract = orch.extract_subtitle_track
    original_write = orch.write_candidate_srt

    def forbidden(*args, **kwargs):
        raise AssertionError("inspect_only must not execute source extraction or writes")

    orch.extract_subtitle_track = forbidden
    orch.write_candidate_srt = forbidden
    try:
        meta = orch.run_generate(media, cfg, inspect_only=True)
    finally:
        orch.extract_subtitle_track = original_extract
        orch.write_candidate_srt = original_write

    assert meta["inspect_only"] is True
    assert meta["executed"] is False
    assert meta["strategy"] == "embedded_en"
    assert meta["registry_run_id"] is None
    assert meta["selection_report"]["selected_source"] == "embedded_en"
    assert "planned_output_srt" in meta


def test_inspect_only_embedded_jp_mt_skips_mt_llm_and_writes():
    """Inspect-only should choose the JA subtitle MT plan without running MT/LLM/write steps."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=True, jp_audio=False)
    originals = (
        orch.extract_subtitle_track,
        orch.translate_candidate_jp_to_en_workflow,
        orch.polish_candidate_with_llm,
        orch.write_candidate_srt,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("inspect_only must not execute subtitle extraction, MT, LLM, or writes")

    (
        orch.extract_subtitle_track,
        orch.translate_candidate_jp_to_en_workflow,
        orch.polish_candidate_with_llm,
        orch.write_candidate_srt,
    ) = (forbidden, forbidden, forbidden, forbidden)
    try:
        meta = orch.run_generate(media, cfg, inspect_only=True)
    finally:
        (
            orch.extract_subtitle_track,
            orch.translate_candidate_jp_to_en_workflow,
            orch.polish_candidate_with_llm,
            orch.write_candidate_srt,
        ) = originals

    assert meta["strategy"] == "embedded_jp_mt"
    assert meta["inspect_only"] is True
    assert meta["selection_report"]["review_recommended"] is True


def test_inspect_only_ja_audio_skips_asr_mt_llm_and_writes():
    """Inspect-only should choose the JA audio plan without touching audio or models."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=True)
    originals = (
        orch.extract_audio_with_ffmpeg,
        orch.FasterWhisperASR,
        orch.translate_candidate_jp_to_en_workflow,
        orch.polish_candidate_with_llm,
        orch.write_candidate_srt,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("inspect_only must not execute audio extraction, ASR, MT, LLM, or writes")

    (
        orch.extract_audio_with_ffmpeg,
        orch.FasterWhisperASR,
        orch.translate_candidate_jp_to_en_workflow,
        orch.polish_candidate_with_llm,
        orch.write_candidate_srt,
    ) = (forbidden, forbidden, forbidden, forbidden, forbidden)
    try:
        meta = orch.run_generate(media, cfg, inspect_only=True)
    finally:
        (
            orch.extract_audio_with_ffmpeg,
            orch.FasterWhisperASR,
            orch.translate_candidate_jp_to_en_workflow,
            orch.polish_candidate_with_llm,
            orch.write_candidate_srt,
        ) = originals

    assert meta["strategy"] == "ja_audio_asr_mt"
    assert meta["inspect_only"] is True


def test_inspect_only_untagged_audio_uses_heuristic_without_probe():
    """Untagged inspect-only should expose the low-confidence fallback without ASR probing."""
    from media_inspect import AudioStream

    cfg = Config()
    media = MediaInfo(
        path=Path("untagged.mkv"),
        format_name="matroska",
        duration=120.0,
        audio_streams=[AudioStream(index=0, codec="aac", language=None)],
        subtitle_streams=[],
    )
    original_asr = orch.FasterWhisperASR

    def forbidden(*args, **kwargs):
        raise AssertionError("inspect_only must not instantiate ASR for language probing")

    orch.FasterWhisperASR = forbidden
    try:
        meta = orch.run_generate(media, cfg, inspect_only=True)
    finally:
        orch.FasterWhisperASR = original_asr

    assert meta["strategy"] == "untagged_audio_asr_mt"
    report = meta["selection_report"]
    assert report["confidence_tier"] == "very_low"
    assert report["review_recommended"] is True
    assert any(
        source["source"] == "untagged_audio_asr_mt"
        and source["status"] == "selected"
        for source in report["sources_evaluated"]
    )


def test_inspect_only_no_usable_source_error_case():
    """Inspect-only should fail clearly when no source can be planned."""
    cfg = Config()
    media = _media(en_sub=False, en_audio=False, jp_sub=False, jp_audio=False)

    try:
        orch.run_generate(media, cfg, inspect_only=True)
    except RuntimeError as exc:
        assert "No usable source found" in str(exc)
    else:
        raise AssertionError("Expected inspect-only mode to reject media with no usable sources")


# ---------------------------------------------------------------------------
# PolicyEngine unit tests (core.policy)
# ---------------------------------------------------------------------------

def test_policy_engine_pass_decision():
    """High-scoring, non-MT candidate must receive a PASS routing decision."""
    from core.policy import PolicyEngine
    engine = PolicyEngine()
    score = {"total_score": 80.0, "grade": "A"}
    report = {"review_recommended": False, "review_reason": None}
    result = engine.route(score, report)
    assert result["decision"] == "pass", result
    assert result["reasons"] == [], result
    assert result["triggered_by"] == [], result
    print("✓ PolicyEngine: high-confidence candidate → PASS")


def test_policy_engine_review_due_to_low_score():
    """Candidate with score below review threshold must route to REVIEW."""
    from core.policy import PolicyEngine
    engine = PolicyEngine()
    score = {"total_score": 45.0, "grade": "C"}
    report = {"review_recommended": False, "review_reason": None}
    result = engine.route(score, report)
    assert result["decision"] == "review", result
    assert "score_below_review_threshold" in result["triggered_by"], result
    print("✓ PolicyEngine: low-score candidate → REVIEW")


def test_policy_engine_review_due_to_review_recommended():
    """MT-strategy candidate must route to REVIEW even when score is above review threshold."""
    from core.policy import PolicyEngine
    engine = PolicyEngine()
    # embedded_jp_mt base score is 40; with neutral QC/yield ~60, borderline —
    # use a score just above the threshold to verify that review_recommended alone triggers REVIEW.
    score = {"total_score": 65.0, "grade": "B"}
    report = {
        "review_recommended": True,
        "review_reason": "MT pipeline output; manual review recommended",
    }
    result = engine.route(score, report)
    assert result["decision"] == "review", result
    assert "review_recommended" in result["triggered_by"], result
    print("✓ PolicyEngine: review_recommended candidate → REVIEW regardless of score")


def test_policy_engine_reject_decision():
    """Candidate with score below reject threshold must route to REJECT."""
    from core.policy import PolicyEngine
    engine = PolicyEngine()
    score = {"total_score": 10.0, "grade": "F"}
    report = {"review_recommended": False, "review_reason": None}
    result = engine.route(score, report)
    assert result["decision"] == "reject", result
    assert "score_below_reject_threshold" in result["triggered_by"], result
    print("✓ PolicyEngine: very-low-score candidate → REJECT")


def test_policy_engine_custom_thresholds():
    """Custom threshold overrides must be respected."""
    from core.policy import PolicyEngine
    cfg = Config()
    cfg._config.setdefault("policy", {})
    cfg._config["policy"]["routing"] = {
        "review_score_threshold": 50,
        "reject_score_threshold": 10,
    }
    engine = PolicyEngine(cfg)
    # score=45 should be below custom review threshold (50) → REVIEW
    score = {"total_score": 45.0, "grade": "C"}
    report = {"review_recommended": False, "review_reason": None}
    result = engine.route(score, report)
    assert result["decision"] == "review", result
    # score=5 should be below custom reject threshold (10) → REJECT
    score_low = {"total_score": 5.0, "grade": "F"}
    result_low = engine.route(score_low, report)
    assert result_low["decision"] == "reject", result_low
    print("✓ PolicyEngine: custom thresholds respected")


def test_policy_engine_translation_qc_warn_and_fail_thresholds():
    """Translation QC warn/fail status should drive REVIEW/REJECT decisions."""
    from core.policy import PolicyEngine

    cfg = Config()
    cfg._config.setdefault("policy", {})
    cfg._config["policy"]["routing"] = {
        "review_score_threshold": 60,
        "reject_score_threshold": 20,
        "translation_qc_review_statuses": ["warn"],
        "translation_qc_warn_review_min_count": 1,
        "translation_qc_reject_statuses": ["fail"],
        "translation_qc_fail_reject_min_count": 1,
    }
    engine = PolicyEngine(cfg)
    report = {"review_recommended": False, "review_reason": None}

    warn_score = {
        "total_score": 95.0,
        "grade": "A",
        "translation_qc_status": "warn",
        "translation_qc_warning_count": 2,
        "translation_qc_fail_count": 0,
    }
    warn_result = engine.route(warn_score, report)
    assert warn_result["decision"] == "review", warn_result
    assert "translation_qc_warn" in warn_result["triggered_by"], warn_result

    fail_score = {
        "total_score": 95.0,
        "grade": "A",
        "translation_qc_status": "fail",
        "translation_qc_warning_count": 0,
        "translation_qc_fail_count": 1,
    }
    fail_result = engine.route(fail_score, report)
    assert fail_result["decision"] == "reject", fail_result
    assert "translation_qc_fail" in fail_result["triggered_by"], fail_result


# ---------------------------------------------------------------------------
# Routing decision integration tests (run_generate metadata)
# ---------------------------------------------------------------------------

def test_routing_decision_in_metadata():
    """run_generate must include 'routing_decision' in returned metadata."""
    cfg = Config()
    media = _media(en_sub=True)
    meta = orch.run_generate(media, cfg)
    assert "routing_decision" in meta, "routing_decision key missing from metadata"
    rd = meta["routing_decision"]
    assert "decision" in rd, rd
    assert "reasons" in rd, rd
    assert "triggered_by" in rd, rd
    assert "review_task_routing" in meta, "review_task_routing key missing from metadata"
    rr = meta["review_task_routing"]
    assert "status" in rr, rr
    assert "reason_codes" in rr, rr
    assert "review_task" in rr, rr
    print("✓ routing_decision present in run_generate metadata")


def test_routing_decision_pass_for_embedded_en():
    """Embedded EN subtitles (high confidence, no MT) must produce a PASS routing decision."""
    cfg = Config()
    media = _media(en_sub=True)
    meta = orch.run_generate(media, cfg)
    rd = meta["routing_decision"]
    assert rd["decision"] == "pass", rd
    assert rd["triggered_by"] == [], rd
    print("✓ embedded_en strategy → routing decision PASS")


def test_routing_decision_review_for_mt_strategies():
    """MT strategies (embedded_jp_mt, ja_audio_asr_mt) must route to REVIEW."""
    cfg = Config()
    mt_cases = [
        (_media(jp_sub=True), "embedded_jp_mt"),
        (_media(jp_audio=True), "ja_audio_asr_mt"),
    ]
    for media, expected_strategy in mt_cases:
        meta = orch.run_generate(media, cfg)
        assert meta["strategy"] == expected_strategy, meta["strategy"]
        rd = meta["routing_decision"]
        assert rd["decision"] == "review", (
            f"{expected_strategy}: expected REVIEW but got {rd['decision']!r}"
        )
        assert "review_recommended" in rd["triggered_by"], rd
    print("✓ MT strategies (embedded_jp_mt, ja_audio_asr_mt) → routing decision REVIEW")


def test_routing_decision_not_pass_when_translation_qc_warn(monkeypatch):
    """Translation QC warn must prevent PASS for JP-source strategy outputs."""
    def _warn_translation_qc(*args, **kwargs):
        return {
            "candidate_id": "embedded_jp_mt_s10",
            "qc_status": "warn",
            "score": 0.72,
            "findings": [{"segment_index": 1, "severity": "warning", "code": "possible_omission"}],
            "segment_results": [{"segment_index": 1, "review_required": True, "status": "warn", "finding_count": 1}],
            "summary": {"warning_count": 1, "fail_count": 0, "review_required_segments": 1},
        }

    monkeypatch.setattr(orch, "run_translation_qc", _warn_translation_qc)
    cfg = Config()
    media = _media(jp_sub=True)
    meta = orch.run_generate(media, cfg)
    rd = meta["routing_decision"]
    assert rd["decision"] in ("review", "reject"), rd
    assert "translation_qc_warn" in rd["triggered_by"], rd


def test_qc_json_contains_subtitle_and_translation_qc(monkeypatch):
    """QC sidecar should persist both subtitle_qc and translation_qc with schema_version=2."""
    def _warn_translation_qc(*args, **kwargs):
        return {
            "candidate_id": "embedded_jp_mt_s10",
            "qc_status": "warn",
            "score": 0.72,
            "findings": [{"segment_index": 1, "severity": "warning", "code": "possible_omission"}],
            "segment_results": [{"segment_index": 1, "review_required": True, "status": "warn", "finding_count": 1}],
            "summary": {"warning_count": 1, "fail_count": 0, "review_required_segments": 1},
        }

    monkeypatch.setattr(orch, "run_translation_qc", _warn_translation_qc)
    cfg = Config()
    media = _media(jp_sub=True)
    meta = orch.run_generate(media, cfg)
    qc_payload = json.loads(Path(meta["qc_json"]).read_text(encoding="utf-8"))
    assert qc_payload["schema_version"] == 2, qc_payload
    assert "subtitle_qc" in qc_payload, qc_payload
    assert "translation_qc" in qc_payload, qc_payload
    assert qc_payload["translation_qc"]["qc_status"] == "warn", qc_payload
    assert qc_payload["overall_qc_status"] == "warn", qc_payload


def test_routing_decision_review_for_untagged_audio_fallback():
    """Untagged audio fallback (very_low confidence) must not receive a PASS routing decision."""
    from media_inspect import AudioStream
    untagged_audio_stream = AudioStream(index=0, codec="aac", language=None)
    media = MediaInfo(
        path=Path("untagged.mkv"),
        format_name="matroska",
        duration=120.0,
        audio_streams=[untagged_audio_stream],
        subtitle_streams=[],
    )
    cfg = Config()
    # Simulate an inconclusive language probe so the untagged_audio_asr_mt path is taken.
    DummyASR.probe_result = ("und", 0.3)
    try:
        meta = orch.run_generate(media, cfg)
    finally:
        DummyASR.probe_result = ("en", 0.95)
    assert meta["strategy"] == "untagged_audio_asr_mt", meta["strategy"]
    rd = meta["routing_decision"]
    assert rd["decision"] in ("review", "reject"), (
        f"untagged_audio_asr_mt: expected REVIEW or REJECT but got {rd['decision']!r}"
    )
    # The decision must be driven by either the score or review_recommended
    assert rd["triggered_by"], (
        "untagged_audio_asr_mt: triggered_by must be non-empty"
    )
    print(f"✓ untagged_audio_asr_mt fallback → routing decision {rd['decision'].upper()} (not PASS)")



def test_routing_decision_structure_complete():
    """routing_decision must always have the required keys with correct types."""
    cfg = Config()
    cases = [
        _media(en_sub=True),
        _media(jp_sub=True),
        _media(jp_audio=True),
        _media(en_audio=True),
    ]
    for media in cases:
        meta = orch.run_generate(media, cfg)
        rd = meta["routing_decision"]
        assert rd["decision"] in ("pass", "review", "reject"), rd
        assert isinstance(rd["reasons"], list), rd
        assert isinstance(rd["triggered_by"], list), rd
    print("✓ routing_decision always has valid structure for all strategies")


if __name__ == "__main__":
    run_all_tests()
