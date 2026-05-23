from __future__ import annotations

from pathlib import Path

from core.artifacts import (
    ARTIFACT_TYPE_SRT,
    ArtifactRegistry,
    ReviewTaskRecord,
    SubtitleCandidateRecord,
)
from core.review import (
    approve_review_task,
    create_review_task_from_benchmark_output,
    create_review_task_from_generate_output,
    list_review_history,
    render_local_review_ui,
)
from core.translation import TranslationMemoryStore


def _store_candidate(
    registry: ArtifactRegistry,
    *,
    media_hash: str = "m1",
    source_id: str = "cand_a",
    parent_candidate_id: int | None = None,
) -> SubtitleCandidateRecord:
    return registry.store_candidate(
        SubtitleCandidateRecord(
            media_hash=media_hash,
            source_id=source_id,
            language="en",
            source="mt",
            origin_stream="sub:0",
            model_version="test",
            segments=[
                {"start": 0.0, "end": 1.0, "text": "hello"},
                {"start": 1.2, "end": 2.3, "text": "world"},
            ],
            meta={},
            parent_candidate_id=parent_candidate_id,
        )
    )


def test_create_review_task_from_generate_output_persists_once() -> None:
    with ArtifactRegistry(":memory:") as registry:
        candidate = _store_candidate(registry, source_id="gen_best")
        routing = {
            "status": "review_required",
            "reason_codes": ["qc.warning_density"],
            "review_task": {"mode": "generate"},
        }
        task1 = create_review_task_from_generate_output(
            registry,
            media_hash="m1",
            candidate_db_id=candidate.id,
            routing=routing,
        )
        task2 = create_review_task_from_generate_output(
            registry,
            media_hash="m1",
            candidate_db_id=candidate.id,
            routing=routing,
        )
        assert task1 is not None
        assert task2 is not None
        assert task1.id == task2.id
        assert len(registry.list_review_tasks(media_hash="m1")) == 1


def test_create_review_task_from_benchmark_output_resolves_candidate() -> None:
    with ArtifactRegistry(":memory:") as registry:
        _store_candidate(registry, source_id="ref_en")
        weak_candidate = _store_candidate(registry, source_id="mt_low")
        routing = {
            "status": "review_required",
            "reason_codes": ["benchmark.quality_below_threshold"],
            "review_task": {
                "mode": "benchmark",
                "reference_id": "ref_en",
                "evidence": {"weak_comparisons": [{"cand_id": "mt_low"}]},
            },
        }
        results = {
            "scorecards": [{"id": "ref_en"}, {"id": "mt_low"}],
        }
        task = create_review_task_from_benchmark_output(
            registry,
            media_hash="m1",
            routing=routing,
            results=results,
        )
        assert task is not None
        assert task.candidate_id == weak_candidate.id


def test_approve_review_task_stores_output_and_history(tmp_path: Path) -> None:
    with ArtifactRegistry(":memory:") as registry:
        candidate = registry.store_candidate(
            SubtitleCandidateRecord(
                media_hash="m1",
                source_id="cand_review",
                language="en",
                source="mt",
                origin_stream="sub:0",
                model_version="test",
                segments=[
                    {"start": 0.0, "end": 1.0, "text": "hello", "meta": {"source_text_ja": "こんにちは"}},
                    {"start": 1.2, "end": 2.3, "text": "world", "meta": {"source_text_ja": "世界"}},
                ],
                meta={"domain_pack": "anime", "language_pack": "ja_en", "source_language": "ja"},
            )
        )
        task = registry.create_review_task(
            ReviewTaskRecord(media_hash="m1", candidate_id=candidate.id)
        )
        output_srt = tmp_path / "approved.srt"
        memory = TranslationMemoryStore(tmp_path / "translation_memory.jsonl")

        result = approve_review_task(
            registry,
            task_id=task.id,
            edited_segments={1: "earth"},
            reviewer_notes="looks good",
            output_srt_path=str(output_srt),
            translation_memory=memory,
        )

        assert result["approved_candidate_id"] is not None
        assert result["stored_corrections"] == 1
        assert output_srt.exists()
        latest_srt = registry.get_latest_artifact("m1", ARTIFACT_TYPE_SRT)
        assert latest_srt is not None
        assert latest_srt.candidate_id == result["approved_candidate_id"]
        correction_hits = memory.query(
            source_text="世界",
            source_lang="ja",
            target_lang="en",
            domain="anime",
            language_pack="ja_en",
        )
        assert len(correction_hits) == 1
        assert correction_hits[0]["bad_translation"] == "world"
        assert correction_hits[0]["approved_translation"] == "earth"
        history = list_review_history(registry, task_id=task.id)
        assert history[-1]["action"] == "task_approved"


def test_render_local_review_ui_contains_side_by_side(tmp_path: Path) -> None:
    with ArtifactRegistry(":memory:") as registry:
        base = _store_candidate(registry, source_id="cand_base")
        edit = _store_candidate(
            registry,
            source_id="cand_edit",
            parent_candidate_id=base.id,
        )
        task = registry.create_review_task(
            ReviewTaskRecord(media_hash="m1", candidate_id=edit.id)
        )
        out_path = tmp_path / "review_ui.html"
        render_local_review_ui(
            registry,
            task_id=task.id,
            output_path=str(out_path),
        )
        html_text = out_path.read_text(encoding="utf-8")
        assert "Editable candidate" in html_text
        assert "cand_base" in html_text
        assert "Export edits JSON" in html_text
