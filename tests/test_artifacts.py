"""Unit tests for core.artifacts — ArtifactRegistry and ProcessingLedger.

All tests use an in-memory SQLite database (':memory:') so they are fast,
isolated, and require no filesystem setup.
"""

from __future__ import annotations

import pytest

from core.artifacts import (
    ArtifactRegistry,
    BenchmarkRunRecord,
    CANDIDATE_STATUS_ACCEPTED,
    CANDIDATE_STATUS_FAILED,
    CANDIDATE_STATUS_PENDING,
    CANDIDATE_STATUS_REVIEW_REQUIRED,
    MediaAssetRecord,
    ProcessingLedger,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_REPROCESS,
    ReviewTaskRecord,
    StreamAssetRecord,
    SubtitleCandidateRecord,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registry():
    """Fresh in-memory ArtifactRegistry for each test."""
    with ArtifactRegistry(":memory:") as reg:
        yield reg


@pytest.fixture()
def ledger(registry):
    return ProcessingLedger(registry)


def _make_candidate(media_hash: str = "deadbeef", **kwargs) -> SubtitleCandidateRecord:
    defaults = dict(
        media_hash=media_hash,
        source_id="asr_ja",
        language="ja",
        source="asr",
        origin_stream="audio:0",
        model_version="large-v3",
    )
    defaults.update(kwargs)
    return SubtitleCandidateRecord(**defaults)


# ===========================================================================
# schema / init
# ===========================================================================

class TestSchemaInit:
    def test_registry_opens_without_error(self):
        reg = ArtifactRegistry(":memory:")
        reg.close()

    def test_context_manager_closes_connection(self):
        with ArtifactRegistry(":memory:") as reg:
            assert reg is not None
        # After exit the connection should be closed; any further use raises.
        with pytest.raises(Exception):
            reg.list_media_assets()


# ===========================================================================
# MediaAsset
# ===========================================================================

class TestMediaAsset:
    def test_upsert_creates_record(self, registry):
        asset = registry.upsert_media_asset(
            media_hash="abc123",
            file_path="/data/ep01.mkv",
            file_name="ep01.mkv",
        )
        assert asset.id is not None
        assert asset.media_hash == "abc123"
        assert asset.file_path == "/data/ep01.mkv"
        assert asset.file_name == "ep01.mkv"
        assert asset.duration_sec is None
        assert asset.created_at is not None

    def test_upsert_with_duration(self, registry):
        asset = registry.upsert_media_asset(
            media_hash="xyz",
            file_path="/data/ep02.mkv",
            file_name="ep02.mkv",
            duration_sec=1440.5,
        )
        assert asset.duration_sec == pytest.approx(1440.5)

    def test_upsert_on_collision_updates_path(self, registry):
        registry.upsert_media_asset(
            media_hash="abc123",
            file_path="/old/path.mkv",
            file_name="old.mkv",
        )
        updated = registry.upsert_media_asset(
            media_hash="abc123",
            file_path="/new/path.mkv",
            file_name="new.mkv",
        )
        assert updated.file_path == "/new/path.mkv"
        assert updated.file_name == "new.mkv"

    def test_get_media_asset_returns_record(self, registry):
        registry.upsert_media_asset(
            media_hash="abc123", file_path="/d/f.mkv", file_name="f.mkv"
        )
        found = registry.get_media_asset("abc123")
        assert found is not None
        assert found.media_hash == "abc123"

    def test_get_media_asset_missing_returns_none(self, registry):
        assert registry.get_media_asset("nonexistent") is None

    def test_list_media_assets_empty(self, registry):
        assert registry.list_media_assets() == []

    def test_list_media_assets_multiple(self, registry):
        registry.upsert_media_asset(media_hash="h1", file_path="/a", file_name="a")
        registry.upsert_media_asset(media_hash="h2", file_path="/b", file_name="b")
        assets = registry.list_media_assets()
        assert len(assets) == 2
        hashes = {a.media_hash for a in assets}
        assert hashes == {"h1", "h2"}


# ===========================================================================
# StreamAsset
# ===========================================================================

class TestStreamAsset:
    def test_store_and_retrieve_stream_asset(self, registry):
        media = registry.upsert_media_asset(
            media_hash="mh1", file_path="/f.mkv", file_name="f.mkv"
        )
        stream = registry.store_stream_asset(
            StreamAssetRecord(
                media_asset_id=media.id,
                stream_index=0,
                stream_type="audio",
                language="ja",
                codec="aac",
                title="Japanese",
            )
        )
        assert stream.id is not None
        assert stream.media_asset_id == media.id
        assert stream.stream_type == "audio"
        assert stream.language == "ja"

    def test_list_stream_assets(self, registry):
        media = registry.upsert_media_asset(
            media_hash="mh2", file_path="/f.mkv", file_name="f.mkv"
        )
        for i, (stream_type, lang) in enumerate([("audio", "ja"), ("subtitle", "en"), ("video", None)]):
            registry.store_stream_asset(
                StreamAssetRecord(
                    media_asset_id=media.id,
                    stream_index=i,
                    stream_type=stream_type,
                    language=lang,
                )
            )
        streams = registry.list_stream_assets(media.id)
        assert len(streams) == 3
        assert streams[0].stream_type == "audio"
        assert streams[1].stream_type == "subtitle"

    def test_list_stream_assets_empty(self, registry):
        assert registry.list_stream_assets(9999) == []


# ===========================================================================
# SubtitleCandidate
# ===========================================================================

class TestSubtitleCandidate:
    def test_store_candidate_returns_record_with_id(self, registry):
        cand = registry.store_candidate(_make_candidate())
        assert cand.id is not None
        assert cand.status == CANDIDATE_STATUS_PENDING

    def test_store_candidate_with_segments(self, registry):
        segs = [{"start": 0.0, "end": 2.0, "text": "こんにちは"}]
        cand = registry.store_candidate(_make_candidate(segments=segs))
        assert cand.segments == segs

    def test_store_candidate_with_meta(self, registry):
        meta = {"model": "whisper", "temperature": 0.0}
        cand = registry.store_candidate(_make_candidate(meta=meta))
        assert cand.meta == meta

    def test_get_candidate_by_id(self, registry):
        stored = registry.store_candidate(_make_candidate())
        found = registry.get_candidate(stored.id)
        assert found is not None
        assert found.id == stored.id
        assert found.source_id == "asr_ja"

    def test_get_candidate_missing_returns_none(self, registry):
        assert registry.get_candidate(9999) is None

    def test_list_candidates_by_media_hash(self, registry):
        registry.store_candidate(_make_candidate("h1", source_id="asr_ja"))
        registry.store_candidate(_make_candidate("h1", source_id="mt_en"))
        registry.store_candidate(_make_candidate("h2", source_id="asr_ja"))
        cands = registry.list_candidates("h1")
        assert len(cands) == 2
        assert all(c.media_hash == "h1" for c in cands)

    def test_list_candidates_filtered_by_status(self, registry):
        c1 = registry.store_candidate(_make_candidate("h1"))
        c2 = registry.store_candidate(_make_candidate("h1"))
        registry.update_candidate_status(c1.id, CANDIDATE_STATUS_ACCEPTED)
        accepted = registry.list_candidates("h1", status=CANDIDATE_STATUS_ACCEPTED)
        pending = registry.list_candidates("h1", status=CANDIDATE_STATUS_PENDING)
        assert len(accepted) == 1
        assert accepted[0].id == c1.id
        assert len(pending) == 1
        assert pending[0].id == c2.id

    def test_update_candidate_status(self, registry):
        cand = registry.store_candidate(_make_candidate())
        registry.update_candidate_status(cand.id, CANDIDATE_STATUS_FAILED)
        updated = registry.get_candidate(cand.id)
        assert updated.status == CANDIDATE_STATUS_FAILED

    def test_update_candidate_status_all_valid_values(self, registry):
        for status in [
            CANDIDATE_STATUS_ACCEPTED,
            CANDIDATE_STATUS_FAILED,
            CANDIDATE_STATUS_REVIEW_REQUIRED,
            CANDIDATE_STATUS_PENDING,
        ]:
            cand = registry.store_candidate(_make_candidate())
            registry.update_candidate_status(cand.id, status)
            assert registry.get_candidate(cand.id).status == status

    def test_update_candidate_status_invalid_raises(self, registry):
        cand = registry.store_candidate(_make_candidate())
        with pytest.raises(ValueError, match="Invalid candidate status"):
            registry.update_candidate_status(cand.id, "bogus_status")

    def test_update_candidate_missing_id_raises(self, registry):
        with pytest.raises(LookupError):
            registry.update_candidate_status(9999, CANDIDATE_STATUS_ACCEPTED)

    def test_store_candidate_invalid_status_raises(self, registry):
        with pytest.raises(ValueError, match="Invalid candidate status"):
            registry.store_candidate(_make_candidate(status="invalid"))


# ===========================================================================
# BenchmarkRun
# ===========================================================================

class TestBenchmarkRun:
    def test_record_and_retrieve_benchmark_run(self, registry):
        run = registry.record_benchmark_run(
            BenchmarkRunRecord(
                media_hash="h1",
                run_id="run-001",
                metrics={"wer": 0.15, "bleu": 70.2, "chrf": 65.0},
            )
        )
        assert run.id is not None
        assert run.run_id == "run-001"
        assert run.wer == pytest.approx(0.15)
        assert run.bleu == pytest.approx(70.2)
        assert run.chrf == pytest.approx(65.0)

    def test_get_benchmark_run_by_run_id(self, registry):
        registry.record_benchmark_run(
            BenchmarkRunRecord(media_hash="h1", run_id="run-001", metrics={})
        )
        found = registry.get_benchmark_run("run-001")
        assert found is not None
        assert found.run_id == "run-001"

    def test_get_benchmark_run_missing_returns_none(self, registry):
        assert registry.get_benchmark_run("nonexistent") is None

    def test_duplicate_run_id_raises(self, registry):
        registry.record_benchmark_run(
            BenchmarkRunRecord(media_hash="h1", run_id="dup", metrics={})
        )
        with pytest.raises(ValueError, match="already exists"):
            registry.record_benchmark_run(
                BenchmarkRunRecord(media_hash="h1", run_id="dup", metrics={})
            )

    def test_list_benchmark_runs(self, registry):
        registry.record_benchmark_run(
            BenchmarkRunRecord(media_hash="h1", run_id="r1", metrics={"wer": 0.3})
        )
        registry.record_benchmark_run(
            BenchmarkRunRecord(media_hash="h1", run_id="r2", metrics={"wer": 0.2})
        )
        registry.record_benchmark_run(
            BenchmarkRunRecord(media_hash="h2", run_id="r3", metrics={})
        )
        runs = registry.list_benchmark_runs("h1")
        assert len(runs) == 2
        assert all(r.media_hash == "h1" for r in runs)

    def test_benchmark_run_metrics_persisted_as_json(self, registry):
        metrics = {"wer": 0.1, "bleu": 80.0, "chrf": 75.5, "extra": "data"}
        run = registry.record_benchmark_run(
            BenchmarkRunRecord(media_hash="h1", run_id="r-json", metrics=metrics)
        )
        fetched = registry.get_benchmark_run("r-json")
        assert fetched.metrics == metrics

    def test_benchmark_run_with_candidate_references(self, registry):
        ref = registry.store_candidate(_make_candidate("h1", source_id="ref"))
        hyp = registry.store_candidate(_make_candidate("h1", source_id="hyp"))
        run = registry.record_benchmark_run(
            BenchmarkRunRecord(
                media_hash="h1",
                run_id="r-refs",
                metrics={},
                reference_candidate_id=ref.id,
                hypothesis_candidate_id=hyp.id,
            )
        )
        fetched = registry.get_benchmark_run("r-refs")
        assert fetched.reference_candidate_id == ref.id
        assert fetched.hypothesis_candidate_id == hyp.id


# ===========================================================================
# ReviewTask
# ===========================================================================

class TestReviewTask:
    def _store_cand(self, registry):
        return registry.store_candidate(_make_candidate())

    def test_create_and_retrieve_review_task(self, registry):
        cand = self._store_cand(registry)
        task = registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand.id)
        )
        assert task.id is not None
        assert task.status == REVIEW_STATUS_PENDING
        assert task.candidate_id == cand.id

    def test_get_review_task_by_id(self, registry):
        cand = self._store_cand(registry)
        task = registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand.id)
        )
        found = registry.get_review_task(task.id)
        assert found.id == task.id

    def test_get_review_task_missing_returns_none(self, registry):
        assert registry.get_review_task(9999) is None

    def test_update_review_task_status(self, registry):
        cand = self._store_cand(registry)
        task = registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand.id)
        )
        registry.update_review_task(task.id, status=REVIEW_STATUS_APPROVED)
        updated = registry.get_review_task(task.id)
        assert updated.status == REVIEW_STATUS_APPROVED

    def test_update_review_task_with_reprocess_reason(self, registry):
        cand = self._store_cand(registry)
        task = registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand.id)
        )
        registry.update_review_task(
            task.id,
            status=REVIEW_STATUS_REPROCESS,
            reprocess_reason="too many gaps in timing",
        )
        updated = registry.get_review_task(task.id)
        assert updated.status == REVIEW_STATUS_REPROCESS
        assert updated.reprocess_reason == "too many gaps in timing"

    def test_update_review_task_invalid_status_raises(self, registry):
        cand = self._store_cand(registry)
        task = registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand.id)
        )
        with pytest.raises(ValueError, match="Invalid review status"):
            registry.update_review_task(task.id, status="invalid_status")

    def test_update_review_task_missing_id_raises(self, registry):
        with pytest.raises(LookupError):
            registry.update_review_task(9999, status=REVIEW_STATUS_APPROVED)

    def test_list_review_tasks_by_media_hash(self, registry):
        cand1 = registry.store_candidate(_make_candidate("h1"))
        cand2 = registry.store_candidate(_make_candidate("h2"))
        registry.create_review_task(ReviewTaskRecord(media_hash="h1", candidate_id=cand1.id))
        registry.create_review_task(ReviewTaskRecord(media_hash="h2", candidate_id=cand2.id))
        tasks_h1 = registry.list_review_tasks(media_hash="h1")
        assert len(tasks_h1) == 1
        assert tasks_h1[0].media_hash == "h1"

    def test_list_review_tasks_by_status(self, registry):
        cand1 = registry.store_candidate(_make_candidate("h1"))
        cand2 = registry.store_candidate(_make_candidate("h1"))
        t1 = registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand1.id)
        )
        registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand2.id)
        )
        registry.update_review_task(t1.id, status=REVIEW_STATUS_APPROVED)
        pending = registry.list_review_tasks(status=REVIEW_STATUS_PENDING)
        approved = registry.list_review_tasks(status=REVIEW_STATUS_APPROVED)
        assert len(pending) == 1
        assert len(approved) == 1

    def test_create_review_task_invalid_status_raises(self, registry):
        cand = self._store_cand(registry)
        with pytest.raises(ValueError, match="Invalid review status"):
            registry.create_review_task(
                ReviewTaskRecord(media_hash="h1", candidate_id=cand.id, status="bad")
            )


# ===========================================================================
# ProcessingLedger
# ===========================================================================

class TestProcessingLedger:
    def test_processed_media_hashes_empty(self, ledger):
        assert ledger.processed_media_hashes() == []

    def test_processed_media_hashes_reflects_stored_assets(self, registry, ledger):
        registry.upsert_media_asset(media_hash="h1", file_path="/a", file_name="a")
        registry.upsert_media_asset(media_hash="h2", file_path="/b", file_name="b")
        hashes = ledger.processed_media_hashes()
        assert set(hashes) == {"h1", "h2"}

    def test_is_processed_false_when_no_candidates(self, registry, ledger):
        registry.upsert_media_asset(media_hash="h1", file_path="/a", file_name="a")
        assert not ledger.is_processed("h1")

    def test_is_processed_true_when_candidates_exist(self, registry, ledger):
        registry.store_candidate(_make_candidate("h1"))
        assert ledger.is_processed("h1")

    def test_accepted_candidates(self, registry, ledger):
        c1 = registry.store_candidate(_make_candidate("h1"))
        c2 = registry.store_candidate(_make_candidate("h1"))
        registry.update_candidate_status(c1.id, CANDIDATE_STATUS_ACCEPTED)
        accepted = ledger.accepted_candidates("h1")
        assert len(accepted) == 1
        assert accepted[0].id == c1.id

    def test_failed_candidates(self, registry, ledger):
        c1 = registry.store_candidate(_make_candidate("h1"))
        registry.update_candidate_status(c1.id, CANDIDATE_STATUS_FAILED)
        failed = ledger.failed_candidates("h1")
        assert len(failed) == 1

    def test_review_required_candidates(self, registry, ledger):
        c1 = registry.store_candidate(_make_candidate("h1"))
        registry.update_candidate_status(c1.id, CANDIDATE_STATUS_REVIEW_REQUIRED)
        review = ledger.review_required_candidates("h1")
        assert len(review) == 1

    def test_pending_review_tasks(self, registry, ledger):
        cand = registry.store_candidate(_make_candidate("h1"))
        t1 = registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand.id)
        )
        registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand.id)
        )
        registry.update_review_task(t1.id, status=REVIEW_STATUS_APPROVED)
        pending = ledger.pending_review_tasks()
        assert len(pending) == 1

    def test_latest_benchmark_run_none_when_empty(self, ledger):
        assert ledger.latest_benchmark_run("h1") is None

    def test_latest_benchmark_run_returns_last(self, registry, ledger):
        registry.record_benchmark_run(
            BenchmarkRunRecord(media_hash="h1", run_id="r1", metrics={"wer": 0.3})
        )
        registry.record_benchmark_run(
            BenchmarkRunRecord(media_hash="h1", run_id="r2", metrics={"wer": 0.2})
        )
        latest = ledger.latest_benchmark_run("h1")
        assert latest.run_id == "r2"

    def test_benchmark_summary_empty(self, ledger):
        summary = ledger.benchmark_summary("h_missing")
        assert summary["run_count"] == 0
        assert summary["best_wer"] is None

    def test_benchmark_summary_values(self, registry, ledger):
        registry.record_benchmark_run(
            BenchmarkRunRecord(media_hash="h1", run_id="r1", metrics={"wer": 0.3, "bleu": 60.0, "chrf": 55.0})
        )
        registry.record_benchmark_run(
            BenchmarkRunRecord(media_hash="h1", run_id="r2", metrics={"wer": 0.1, "bleu": 80.0, "chrf": 75.0})
        )
        summary = ledger.benchmark_summary("h1")
        assert summary["run_count"] == 2
        assert summary["best_wer"] == pytest.approx(0.1)
        assert summary["best_bleu"] == pytest.approx(80.0)
        assert summary["best_chrf"] == pytest.approx(75.0)

    def test_reprocess_candidates(self, registry, ledger):
        cand = registry.store_candidate(_make_candidate("h1"))
        task = registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand.id)
        )
        registry.update_review_task(
            task.id, status=REVIEW_STATUS_REPROCESS, reprocess_reason="timing off"
        )
        reprocess = ledger.reprocess_candidates("h1")
        assert len(reprocess) == 1
        assert reprocess[0].id == cand.id
