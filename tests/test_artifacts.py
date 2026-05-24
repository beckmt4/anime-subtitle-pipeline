"""Unit tests for core.artifacts — ArtifactRegistry and ProcessingLedger.

All tests use an in-memory SQLite database (':memory:') so they are fast,
isolated, and require no filesystem setup.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.artifacts import (
    ARTIFACT_TYPE_MKV,
    ARTIFACT_TYPE_SRT,
    ArtifactRecord,
    ArtifactRegistry,
    BenchmarkRunRecord,
    CANDIDATE_STATUS_ACCEPTED,
    CANDIDATE_STATUS_FAILED,
    CANDIDATE_STATUS_PENDING,
    CANDIDATE_STATUS_REVIEW_REQUIRED,
    MediaAssetRecord,
    PIPELINE_STATUS_COMPLETED,
    PIPELINE_STATUS_FAILED,
    PipelineRunRecord,
    ProcessingLedger,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_REPROCESS,
    ReviewTaskRecord,
    StreamAssetRecord,
    SubtitleCandidateRecord,
)
from core.artifacts.schema import init_db


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

    def test_schema_migrations_table_exists(self):
        conn = init_db(":memory:")
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("schema_migrations",),
        ).fetchone()
        assert row["name"] == "schema_migrations"
        conn.close()

    def test_applies_sql_migrations_from_directory(self, tmp_path):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        (migrations / "001_add_probe_table.sql").write_text(
            """
            CREATE TABLE migration_probe (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            INSERT INTO migration_probe (name) VALUES ('applied');
            """,
            encoding="utf-8",
        )

        conn = init_db(tmp_path / "pipeline.db", migrations_dir=migrations)
        probe = conn.execute("SELECT name FROM migration_probe").fetchone()
        applied = conn.execute(
            "SELECT filename FROM schema_migrations ORDER BY filename"
        ).fetchall()

        assert probe["name"] == "applied"
        assert [row["filename"] for row in applied] == ["001_add_probe_table.sql"]
        conn.close()

    def test_migrations_are_idempotent_for_existing_database(self, tmp_path):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        (migrations / "001_create_counter.sql").write_text(
            """
            CREATE TABLE migration_counter (
                id INTEGER PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO migration_counter (value) VALUES ('once');
            """,
            encoding="utf-8",
        )
        db = tmp_path / "pipeline.db"

        init_db(db, migrations_dir=migrations).close()
        init_db(db, migrations_dir=migrations).close()

        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM migration_counter").fetchone()[0]
        migration_count = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]
        assert count == 1
        assert migration_count == 1
        conn.close()

    def test_applies_pending_migration_to_existing_database(self, tmp_path):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        db = tmp_path / "pipeline.db"
        (migrations / "001_create_first.sql").write_text(
            "CREATE TABLE first_migration (id INTEGER PRIMARY KEY);",
            encoding="utf-8",
        )
        init_db(db, migrations_dir=migrations).close()

        (migrations / "002_create_second.sql").write_text(
            "CREATE TABLE second_migration (id INTEGER PRIMARY KEY);",
            encoding="utf-8",
        )
        conn = init_db(db, migrations_dir=migrations)

        rows = conn.execute(
            "SELECT filename FROM schema_migrations ORDER BY filename"
        ).fetchall()
        assert [row["filename"] for row in rows] == [
            "001_create_first.sql",
            "002_create_second.sql",
        ]
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("second_migration",),
        ).fetchone()
        conn.close()

    def test_changed_applied_migration_checksum_raises(self, tmp_path):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        db = tmp_path / "pipeline.db"
        migration = migrations / "001_create_probe.sql"
        migration.write_text(
            "CREATE TABLE checksum_probe (id INTEGER PRIMARY KEY);",
            encoding="utf-8",
        )
        init_db(db, migrations_dir=migrations).close()

        migration.write_text(
            "CREATE TABLE checksum_probe_changed (id INTEGER PRIMARY KEY);",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="changed checksum"):
            init_db(db, migrations_dir=migrations)


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

    def test_source_language_defaults_to_none(self, registry):
        cand = registry.store_candidate(_make_candidate())
        assert cand.source_language is None

    def test_source_language_roundtrip_for_mt_candidate(self, registry):
        """MT candidates record the language they were translated from."""
        mt_cand = registry.store_candidate(
            _make_candidate(
                source_id="mt_en",
                language="en",
                source="mt",
                source_language="ja",
            )
        )
        assert mt_cand.source_language == "ja"
        retrieved = registry.get_candidate(mt_cand.id)
        assert retrieved.source_language == "ja"

    def test_source_language_roundtrip_for_asr_candidate(self, registry):
        """ASR candidates have source_language=None (source and output are the same)."""
        asr_cand = registry.store_candidate(
            _make_candidate(
                source_id="asr_ja",
                language="ja",
                source="asr",
                source_language=None,
            )
        )
        assert asr_cand.source_language is None
        retrieved = registry.get_candidate(asr_cand.id)
        assert retrieved.source_language is None

    def test_list_candidates_preserves_source_language(self, registry):
        """list_candidates returns source_language on every record."""
        registry.store_candidate(
            _make_candidate("h1", source_id="asr_ja", language="ja", source="asr")
        )
        registry.store_candidate(
            _make_candidate("h1", source_id="mt_en", language="en",
                            source="mt", source_language="ja")
        )
        cands = registry.list_candidates("h1")
        asr_rec = next(c for c in cands if c.source == "asr")
        mt_rec = next(c for c in cands if c.source == "mt")
        assert asr_rec.source_language is None
        assert mt_rec.source_language == "ja"


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
        assert task.history == []

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

    def test_append_review_task_history(self, registry):
        cand = self._store_cand(registry)
        task = registry.create_review_task(
            ReviewTaskRecord(media_hash="h1", candidate_id=cand.id)
        )
        registry.append_review_task_history(
            task.id,
            {"action": "task_created", "details": {"mode": "generate"}},
        )
        updated = registry.get_review_task(task.id)
        assert len(updated.history) == 1
        assert updated.history[0]["action"] == "task_created"

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


# ===========================================================================
# PipelineRun — list_pipeline_runs, artifact queries, candidate lineage
# ===========================================================================

class TestPipelineRunQueries:
    """Tests for the new query methods added in Issue #83/#86."""

    def _create_run(self, registry, run_id, media_hash="h1", status=PIPELINE_STATUS_COMPLETED):
        rec = registry.create_pipeline_run(
            PipelineRunRecord(run_id=run_id, media_hash=media_hash)
        )
        if status != "running":
            registry.finish_pipeline_run(run_id, status=status)
        return rec

    def test_list_pipeline_runs_empty(self, registry):
        assert registry.list_pipeline_runs() == []

    def test_list_pipeline_runs_returns_all(self, registry):
        self._create_run(registry, "r1", "h1")
        self._create_run(registry, "r2", "h2")
        runs = registry.list_pipeline_runs()
        assert len(runs) == 2

    def test_list_pipeline_runs_filter_by_media_hash(self, registry):
        self._create_run(registry, "r1", "h1")
        self._create_run(registry, "r2", "h2")
        runs = registry.list_pipeline_runs(media_hash="h1")
        assert len(runs) == 1
        assert runs[0].run_id == "r1"

    def test_list_pipeline_runs_filter_by_status(self, registry):
        self._create_run(registry, "r1", "h1", status=PIPELINE_STATUS_COMPLETED)
        self._create_run(registry, "r2", "h1", status=PIPELINE_STATUS_FAILED)
        completed = registry.list_pipeline_runs(status=PIPELINE_STATUS_COMPLETED)
        failed = registry.list_pipeline_runs(status=PIPELINE_STATUS_FAILED)
        assert len(completed) == 1
        assert len(failed) == 1

    def test_list_pipeline_runs_limit(self, registry):
        for i in range(5):
            self._create_run(registry, f"r{i}", "h1")
        runs = registry.list_pipeline_runs(limit=3)
        assert len(runs) == 3

    def test_get_runs_for_hash_empty(self, registry):
        assert registry.get_runs_for_hash("unknown") == []

    def test_get_runs_for_hash_returns_runs(self, registry):
        self._create_run(registry, "r1", "h1")
        self._create_run(registry, "r2", "h1")
        self._create_run(registry, "r3", "h2")
        runs = registry.get_runs_for_hash("h1")
        assert len(runs) == 2
        assert all(r.media_hash == "h1" for r in runs)

    def test_get_runs_for_media_hash_alias_returns_runs(self, registry):
        self._create_run(registry, "r1", "h1")
        self._create_run(registry, "r2", "h2")
        runs = registry.get_runs_for_media_hash("h1")
        assert len(runs) == 1
        assert runs[0].run_id == "r1"

    def test_get_latest_artifact_no_match_returns_none(self, registry):
        assert registry.get_latest_artifact("h1", ARTIFACT_TYPE_SRT) is None

    def test_get_latest_artifact_returns_record(self, registry):
        registry.store_artifact(ArtifactRecord(
            media_hash="h1", artifact_type=ARTIFACT_TYPE_SRT, file_path="/out/v1.en.srt"
        ))
        registry.store_artifact(ArtifactRecord(
            media_hash="h1", artifact_type=ARTIFACT_TYPE_SRT, file_path="/out/v2.en.srt"
        ))
        latest = registry.get_latest_artifact("h1", ARTIFACT_TYPE_SRT)
        assert latest is not None
        assert latest.artifact_type == ARTIFACT_TYPE_SRT
        assert latest.file_path == "/out/v2.en.srt"

    def test_get_latest_artifact_filters_type_and_media_hash(self, registry):
        registry.store_artifact(ArtifactRecord(
            media_hash="h1", artifact_type=ARTIFACT_TYPE_MKV, file_path="/out/v1.mkv"
        ))
        registry.store_artifact(ArtifactRecord(
            media_hash="h2", artifact_type=ARTIFACT_TYPE_SRT, file_path="/out/v2.en.srt"
        ))
        assert registry.get_latest_artifact("h1", ARTIFACT_TYPE_SRT) is None

    def test_get_latest_srt_no_artifact_returns_none(self, registry):
        assert registry.get_latest_srt("h1") is None

    def test_get_latest_srt_returns_most_recent(self, registry):
        registry.upsert_media_asset(media_hash="h1", file_path="/v.mkv", file_name="v.mkv")
        registry.store_artifact(ArtifactRecord(
            media_hash="h1", artifact_type=ARTIFACT_TYPE_SRT, file_path="/out/v1.en.srt"
        ))
        registry.store_artifact(ArtifactRecord(
            media_hash="h1", artifact_type=ARTIFACT_TYPE_SRT, file_path="/out/v2.en.srt"
        ))
        # Most recently stored SRT should be returned
        latest = registry.get_latest_srt("h1")
        assert latest == "/out/v2.en.srt"

    def test_get_latest_srt_ignores_other_artifact_types(self, registry):
        registry.upsert_media_asset(media_hash="h1", file_path="/v.mkv", file_name="v.mkv")
        registry.store_artifact(ArtifactRecord(
            media_hash="h1", artifact_type=ARTIFACT_TYPE_MKV, file_path="/out/v.en.mkv"
        ))
        assert registry.get_latest_srt("h1") is None

    def test_get_candidate_chain_missing_candidate_returns_empty(self, registry):
        assert registry.get_candidate_chain(9999) == []

    def test_get_candidate_chain_single_root_candidate(self, registry):
        cand = registry.store_candidate(_make_candidate("h1", source_id="asr_ja"))
        chain = registry.get_candidate_chain(cand.id)
        assert [c.id for c in chain] == [cand.id]

    def test_get_candidate_chain_returns_root_to_leaf(self, registry):
        asr = registry.store_candidate(_make_candidate("h1", source_id="asr_ja"))
        mt = registry.store_candidate(_make_candidate(
            "h1", source_id="mt_en", source="mt", parent_candidate_id=asr.id
        ))
        llm = registry.store_candidate(_make_candidate(
            "h1", source_id="llm_en", source="mt_llm", parent_candidate_id=mt.id
        ))
        chain = registry.get_candidate_chain(llm.id)
        assert [c.id for c in chain] == [asr.id, mt.id, llm.id]
        assert [c.source_id for c in chain] == ["asr_ja", "mt_en", "llm_en"]


class TestArtifactTypeMKV:
    """Tests for the ARTIFACT_TYPE_MKV constant and storage."""

    def test_mkv_constant_value(self):
        assert ARTIFACT_TYPE_MKV == "mkv"

    def test_store_mkv_artifact(self, registry):
        registry.upsert_media_asset(media_hash="h1", file_path="/v.mkv", file_name="v.mkv")
        rec = registry.store_artifact(ArtifactRecord(
            media_hash="h1",
            artifact_type=ARTIFACT_TYPE_MKV,
            file_path="/out/v.en.mkv",
        ))
        assert rec.id is not None
        assert rec.artifact_type == ARTIFACT_TYPE_MKV

    def test_retrieve_mkv_artifact(self, registry):
        registry.upsert_media_asset(media_hash="h1", file_path="/v.mkv", file_name="v.mkv")
        stored = registry.store_artifact(ArtifactRecord(
            media_hash="h1",
            artifact_type=ARTIFACT_TYPE_MKV,
            file_path="/out/v.en.mkv",
        ))
        fetched = registry.get_artifact(stored.id)
        assert fetched.artifact_type == ARTIFACT_TYPE_MKV
        assert fetched.file_path == "/out/v.en.mkv"


class TestProcessingLedgerListRuns:
    """Tests for ProcessingLedger.list_runs() — Issue #83."""

    def test_list_runs_empty(self, ledger):
        assert ledger.list_runs() == []

    def test_list_runs_returns_summary_dicts(self, registry, ledger):
        registry.create_pipeline_run(PipelineRunRecord(run_id="r1", media_hash="h1"))
        registry.finish_pipeline_run("r1", status=PIPELINE_STATUS_COMPLETED)
        runs = ledger.list_runs()
        assert len(runs) == 1
        run = runs[0]
        assert run["run_id"] == "r1"
        assert run["media_hash"] == "h1"
        assert run["status"] == PIPELINE_STATUS_COMPLETED
        assert "created_at" in run
        assert "finished_at" in run
        assert "error_message" in run

    def test_list_runs_filter_by_media_hash(self, registry, ledger):
        registry.create_pipeline_run(PipelineRunRecord(run_id="r1", media_hash="h1"))
        registry.create_pipeline_run(PipelineRunRecord(run_id="r2", media_hash="h2"))
        runs = ledger.list_runs(media_hash="h1")
        assert len(runs) == 1
        assert runs[0]["run_id"] == "r1"

    def test_list_runs_respects_limit(self, registry, ledger):
        for i in range(10):
            registry.create_pipeline_run(PipelineRunRecord(run_id=f"r{i}", media_hash="h1"))
        runs = ledger.list_runs(limit=4)
        assert len(runs) == 4

    def test_list_pipeline_runs_alias_returns_summary_dicts(self, registry, ledger):
        registry.create_pipeline_run(PipelineRunRecord(run_id="r1", media_hash="h1"))
        registry.finish_pipeline_run("r1", status=PIPELINE_STATUS_COMPLETED)
        runs = ledger.list_pipeline_runs()
        assert len(runs) == 1
        assert runs[0]["run_id"] == "r1"
        assert runs[0]["status"] == PIPELINE_STATUS_COMPLETED

    def test_list_pipeline_runs_includes_failed_status_and_error(self, registry, ledger):
        registry.create_pipeline_run(PipelineRunRecord(run_id="r1", media_hash="h1"))
        registry.finish_pipeline_run(
            "r1",
            status=PIPELINE_STATUS_FAILED,
            error_message="ASR failed",
        )
        runs = ledger.list_pipeline_runs(media_hash="h1")
        assert len(runs) == 1
        assert runs[0]["status"] == PIPELINE_STATUS_FAILED
        assert runs[0]["error_message"] == "ASR failed"

    def test_get_latest_run_for_media_empty(self, ledger):
        assert ledger.get_latest_run_for_media("missing") is None

    def test_get_latest_run_for_media_returns_newest(self, registry, ledger):
        registry.create_pipeline_run(PipelineRunRecord(run_id="r1", media_hash="h1"))
        registry.create_pipeline_run(PipelineRunRecord(run_id="r2", media_hash="h1"))
        latest = ledger.get_latest_run_for_media("h1")
        assert latest is not None
        assert latest.run_id == "r2"
