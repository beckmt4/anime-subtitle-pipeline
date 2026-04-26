"""Tests for core.artifacts.pipeline_wiring and the _reg_* helpers in orchestrator.

Covers:
- compute_media_hash: correct SHA-256, chunked reading, error propagation
- open_registry: returns ArtifactRegistry on valid path, None on bad path
- _reg_store_candidate: stores correctly, returns db_id, returns None when
  registry is None, returns None on unexpected error
- _reg_store_artifact: stores SRT/QC artifacts, computes file_hash
- _reg_start_run / _reg_finish_run: creates and finishes pipeline run records
- Backward compatibility: all _reg_* helpers accept registry=None silently
- End-to-end candidate lineage: ASR -> MT -> LLM chain has correct parent ids
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.artifacts import (
    ArtifactRegistry,
    ARTIFACT_TYPE_QC_JSON,
    ARTIFACT_TYPE_SRT,
    CANDIDATE_STATUS_ACCEPTED,
    PIPELINE_STATUS_COMPLETED,
    PIPELINE_STATUS_FAILED,
)
from core.artifacts.pipeline_wiring import compute_media_hash, open_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_segment(start=0.0, end=1.0, text="hello"):
    """Return a minimal models.Segment-compatible object."""
    seg = MagicMock()
    seg.start = start
    seg.end = end
    seg.text = text
    return seg


def _make_candidate(cid="asr_ja", language="ja", source="asr",
                    origin_stream="audio:0", segments=None, meta=None):
    """Return a minimal models.SubtitleCandidate-compatible object."""
    c = MagicMock()
    c.id = cid
    c.language = language
    c.source = source
    c.origin_stream = origin_stream
    c.segments = segments or [_make_segment()]
    c.meta = meta or {}
    return c


def _make_cfg(db_path=":memory:", model_name="large-v3",
              mt_model="Helsinki-NLP/opus-mt-ja-en",
              llm_model="qwen2.5:7b"):
    """Return a minimal Config-compatible mock."""
    cfg = MagicMock()
    cfg.artifacts_db_path = db_path
    cfg.profile = "test"
    cfg.asr_model_name = model_name
    cfg.mt_model_name = mt_model
    cfg.llm_model_name = llm_model
    cfg.llm_enabled = True
    return cfg


# ---------------------------------------------------------------------------
# compute_media_hash
# ---------------------------------------------------------------------------

class TestComputeMediaHash:
    def test_correct_sha256(self, tmp_path):
        """Hash of a known byte string matches hashlib directly."""
        data = b"anime subtitle pipeline test data"
        p = tmp_path / "test.bin"
        p.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert compute_media_hash(p) == expected

    def test_returns_64_char_hex(self, tmp_path):
        p = tmp_path / "f.bin"
        p.write_bytes(b"\x00" * 100)
        result = compute_media_hash(p)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.bin"
        p.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_media_hash(p) == expected

    def test_large_file_chunked(self, tmp_path):
        """Files larger than 1 MiB are hashed correctly (chunk boundary test)."""
        data = b"x" * (2 << 20)  # 2 MiB
        p = tmp_path / "large.bin"
        p.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert compute_media_hash(p) == expected

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(OSError):
            compute_media_hash(tmp_path / "does_not_exist.bin")


# ---------------------------------------------------------------------------
# open_registry
# ---------------------------------------------------------------------------

class TestOpenRegistry:
    def test_returns_registry_for_memory_db(self):
        cfg = _make_cfg(db_path=":memory:")
        reg = open_registry(cfg)
        assert reg is not None
        assert isinstance(reg, ArtifactRegistry)

    def test_returns_registry_for_file_path(self, tmp_path):
        db = tmp_path / "test.db"
        cfg = _make_cfg(db_path=str(db))
        reg = open_registry(cfg)
        assert reg is not None
        assert db.exists()

    def test_creates_parent_dir(self, tmp_path):
        db = tmp_path / "sub" / "dir" / "pipeline.db"
        cfg = _make_cfg(db_path=str(db))
        reg = open_registry(cfg)
        assert reg is not None
        assert db.exists()

    def test_returns_none_on_bad_path(self):
        cfg = _make_cfg(db_path="/nonexistent/path/that/cannot/be/created/pipeline.db")
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("no")):
            reg = open_registry(cfg)
        assert reg is None

    def test_returns_none_when_cfg_raises(self):
        cfg = MagicMock()
        cfg.artifacts_db_path = property(lambda self: (_ for _ in ()).throw(RuntimeError("bad")))
        # cfg.artifacts_db_path raises — open_registry should return None
        bad_cfg = MagicMock(spec=[])  # no attributes at all
        result = open_registry(bad_cfg)
        assert result is None


# ---------------------------------------------------------------------------
# _reg_* helpers (imported from orchestrator internals)
# ---------------------------------------------------------------------------

# Import the private helpers directly for unit testing.
from orchestrator import (  # noqa: E402  (after fixtures)
    _reg_finish_run,
    _reg_start_run,
    _reg_store_artifact,
    _reg_store_candidate,
)


class TestRegStoreCandidateHelper:
    def test_returns_none_when_registry_is_none(self):
        cand = _make_candidate()
        result = _reg_store_candidate(None, "abc123", cand, source="asr")
        assert result is None

    def test_returns_none_when_media_hash_is_none(self):
        reg = ArtifactRegistry(":memory:")
        cand = _make_candidate()
        result = _reg_store_candidate(reg, None, cand, source="asr")
        assert result is None

    def test_stores_candidate_and_returns_id(self):
        reg = ArtifactRegistry(":memory:")
        cand = _make_candidate(cid="asr_ja", language="ja", source="asr")
        db_id = _reg_store_candidate(reg, "deadbeef", cand, source="asr",
                                     model_version="large-v3")
        assert isinstance(db_id, int)
        assert db_id > 0

    def test_stored_candidate_has_correct_fields(self):
        reg = ArtifactRegistry(":memory:")
        cand = _make_candidate(cid="asr_ja", language="ja", source="asr",
                               origin_stream="audio:0")
        db_id = _reg_store_candidate(reg, "deadbeef", cand, source="asr",
                                     model_version="large-v3")
        stored = reg.get_candidate(db_id)
        assert stored.source_id == "asr_ja"
        assert stored.language == "ja"
        assert stored.source == "asr"
        assert stored.origin_stream == "audio:0"
        assert stored.model_version == "large-v3"
        assert stored.status == CANDIDATE_STATUS_ACCEPTED
        assert stored.parent_candidate_id is None

    def test_lineage_parent_id_stored(self):
        """MT candidate stores parent_candidate_id pointing to ASR candidate."""
        reg = ArtifactRegistry(":memory:")
        asr_cand = _make_candidate(cid="asr_ja", language="ja", source="asr")
        mt_cand = _make_candidate(cid="asr_ja_mt", language="en", source="mt")
        asr_id = _reg_store_candidate(reg, "abc", asr_cand, source="asr")
        mt_id = _reg_store_candidate(reg, "abc", mt_cand, source="mt",
                                     parent_id=asr_id)
        stored_mt = reg.get_candidate(mt_id)
        assert stored_mt.parent_candidate_id == asr_id

    def test_full_asr_mt_llm_chain(self):
        """Three-step lineage: ASR -> MT -> LLM all with correct parent ids."""
        reg = ArtifactRegistry(":memory:")
        hash_ = "cafebabe"
        asr = _make_candidate("asr_ja", "ja", "asr")
        mt = _make_candidate("asr_ja_mt", "en", "mt")
        llm = _make_candidate("asr_ja_mt_llm", "en", "mt_llm")

        asr_id = _reg_store_candidate(reg, hash_, asr, source="asr")
        mt_id = _reg_store_candidate(reg, hash_, mt, source="mt", parent_id=asr_id)
        llm_id = _reg_store_candidate(reg, hash_, llm, source="mt_llm", parent_id=mt_id)

        stored_asr = reg.get_candidate(asr_id)
        stored_mt = reg.get_candidate(mt_id)
        stored_llm = reg.get_candidate(llm_id)
        assert stored_asr.parent_candidate_id is None
        assert stored_mt.parent_candidate_id == asr_id
        assert stored_llm.parent_candidate_id == mt_id

    def test_returns_none_on_registry_error(self):
        """Registry errors are swallowed and None is returned."""
        reg = MagicMock(spec=ArtifactRegistry)
        reg.store_candidate.side_effect = RuntimeError("db locked")
        cand = _make_candidate()
        result = _reg_store_candidate(reg, "abc", cand, source="asr")
        assert result is None


# ---------------------------------------------------------------------------
# _reg_store_artifact
# ---------------------------------------------------------------------------

class TestRegStoreArtifactHelper:
    def test_returns_none_when_registry_is_none(self, tmp_path):
        p = tmp_path / "out.srt"
        p.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
        result = _reg_store_artifact(None, "abc", ARTIFACT_TYPE_SRT, p)
        assert result is None

    def test_returns_none_when_media_hash_is_none(self, tmp_path):
        p = tmp_path / "out.srt"
        p.write_text("hello")
        reg = ArtifactRegistry(":memory:")
        result = _reg_store_artifact(reg, None, ARTIFACT_TYPE_SRT, p)
        assert result is None

    def test_stores_srt_artifact(self, tmp_path):
        p = tmp_path / "out.srt"
        p.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
        reg = ArtifactRegistry(":memory:")
        art_id = _reg_store_artifact(reg, "abc123", ARTIFACT_TYPE_SRT, p)
        assert isinstance(art_id, int)
        stored = reg.get_artifact(art_id)
        assert stored.artifact_type == ARTIFACT_TYPE_SRT
        assert stored.file_hash is not None
        assert len(stored.file_hash) == 64

    def test_stores_qc_json_artifact(self, tmp_path):
        p = tmp_path / "out.en.qc.json"
        p.write_text('{"issues": []}')
        reg = ArtifactRegistry(":memory:")
        art_id = _reg_store_artifact(reg, "abc123", ARTIFACT_TYPE_QC_JSON, p)
        stored = reg.get_artifact(art_id)
        assert stored.artifact_type == ARTIFACT_TYPE_QC_JSON

    def test_stores_with_candidate_and_run_links(self, tmp_path):
        p = tmp_path / "out.srt"
        p.write_text("hello")
        reg = ArtifactRegistry(":memory:")
        # Create a candidate and pipeline run to link to
        from core.artifacts import (
            SubtitleCandidateRecord, PipelineRunRecord, PIPELINE_STATUS_RUNNING
        )
        cand = SubtitleCandidateRecord(
            media_hash="abc123", source_id="asr_ja", language="ja",
            source="asr", origin_stream="audio:0",
        )
        run = PipelineRunRecord(run_id="run001", media_hash="abc123")
        stored_cand = reg.store_candidate(cand)
        stored_run = reg.create_pipeline_run(run)

        art_id = _reg_store_artifact(
            reg, "abc123", ARTIFACT_TYPE_SRT, p,
            candidate_db_id=stored_cand.id,
            run_db_id=stored_run.id,
        )
        stored = reg.get_artifact(art_id)
        assert stored.candidate_id == stored_cand.id
        assert stored.pipeline_run_id == stored_run.id

    def test_file_hash_is_none_for_missing_file(self, tmp_path):
        """Artifacts for non-existent files store file_hash=None (no crash)."""
        p = tmp_path / "missing.srt"
        reg = ArtifactRegistry(":memory:")
        art_id = _reg_store_artifact(reg, "abc", ARTIFACT_TYPE_SRT, p)
        stored = reg.get_artifact(art_id)
        assert stored.file_hash is None


# ---------------------------------------------------------------------------
# _reg_start_run / _reg_finish_run
# ---------------------------------------------------------------------------

class TestRegRunHelpers:
    def test_start_run_returns_db_id(self):
        reg = ArtifactRegistry(":memory:")
        cfg = _make_cfg()
        run_db_id = _reg_start_run(reg, "deadbeef", cfg, run_id="run001")
        assert isinstance(run_db_id, int)
        assert run_db_id > 0

    def test_start_run_returns_none_when_registry_none(self):
        cfg = _make_cfg()
        result = _reg_start_run(None, "deadbeef", cfg, run_id="run001")
        assert result is None

    def test_start_run_returns_none_when_media_hash_none(self):
        reg = ArtifactRegistry(":memory:")
        cfg = _make_cfg()
        result = _reg_start_run(reg, None, cfg, run_id="run001")
        assert result is None

    def test_finish_run_completed(self):
        reg = ArtifactRegistry(":memory:")
        cfg = _make_cfg()
        _reg_start_run(reg, "deadbeef", cfg, run_id="run001")
        _reg_finish_run(reg, "run001", status=PIPELINE_STATUS_COMPLETED)
        stored = reg.get_pipeline_run("run001")
        assert stored.status == PIPELINE_STATUS_COMPLETED
        assert stored.finished_at is not None

    def test_finish_run_failed_with_message(self):
        reg = ArtifactRegistry(":memory:")
        cfg = _make_cfg()
        _reg_start_run(reg, "deadbeef", cfg, run_id="run002")
        _reg_finish_run(reg, "run002", status=PIPELINE_STATUS_FAILED,
                        error_message="ASR model not found")
        stored = reg.get_pipeline_run("run002")
        assert stored.status == PIPELINE_STATUS_FAILED
        assert stored.error_message == "ASR model not found"

    def test_finish_run_noop_when_registry_none(self):
        # Should not raise.
        _reg_finish_run(None, 42, status=PIPELINE_STATUS_COMPLETED)

    def test_finish_run_noop_when_run_id_none(self):
        reg = ArtifactRegistry(":memory:")
        _reg_finish_run(reg, None, status=PIPELINE_STATUS_COMPLETED)


# ---------------------------------------------------------------------------
# Backward compatibility: registry=None throughout
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_all_helpers_accept_none_registry(self, tmp_path):
        """Passing registry=None to all helpers never raises."""
        cfg = _make_cfg()
        cand = _make_candidate()
        p = tmp_path / "out.srt"
        p.write_text("hello")

        assert _reg_start_run(None, "abc", cfg, run_id="x") is None
        assert _reg_store_candidate(None, "abc", cand, source="asr") is None
        assert _reg_store_artifact(None, "abc", ARTIFACT_TYPE_SRT, p) is None
        _reg_finish_run(None, None, status=PIPELINE_STATUS_COMPLETED)  # no raise
