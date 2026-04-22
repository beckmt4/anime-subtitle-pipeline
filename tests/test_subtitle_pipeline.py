"""Unit tests for subtitle_pipeline — processing verification, logging, exit codes."""

import hashlib
import json
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from subtitle_corrector import CorrectionStats
import subtitle_pipeline as pipeline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_SRT = """\
1
00:00:01,000 --> 00:00:03,000
Hello world.

2
00:00:04,000 --> 00:00:06,000
Goodbye world.
"""

CORRECTED_SRT = """\
1
00:00:01,000 --> 00:00:03,000
Hello, world.

2
00:00:04,000 --> 00:00:06,000
Goodbye, world.
"""

_STATS_CHANGED = CorrectionStats(cues_in=2, cues_out=2, corrected=1, drift_reverted=0)
_STATS_UNCHANGED = CorrectionStats(cues_in=2, cues_out=2, corrected=0, drift_reverted=2)


def _write_srt(path: Path, content: str = MINIMAL_SRT) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# process_file — status: ok
# ---------------------------------------------------------------------------

class TestProcessFileOk:
    def test_writes_output_when_changed(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt")
        out = tmp_path / "ep.corrected.srt"
        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(CORRECTED_SRT, _STATS_CHANGED)):
            status = pipeline.process_file(inp, out, "mistral", str(log))

        assert status == "ok"
        assert out.read_text(encoding="utf-8") == CORRECTED_SRT

    def test_log_entry_ok(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt")
        out = tmp_path / "ep.corrected.srt"
        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(CORRECTED_SRT, _STATS_CHANGED)):
            pipeline.process_file(inp, out, "mistral", str(log))

        entry = json.loads(log.read_text())
        assert entry["status"] == "ok"
        assert entry["file"] == "ep.srt"
        assert entry["cues_in"] == 2
        assert entry["drift_count"] == 0
        assert entry["error"] is None
        assert "retry_with_model" not in entry

    def test_creates_output_dir_if_missing(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt")
        out = tmp_path / "subdir" / "ep.corrected.srt"
        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(CORRECTED_SRT, _STATS_CHANGED)):
            status = pipeline.process_file(inp, out, "mistral", str(log))

        assert status == "ok"
        assert out.exists()


# ---------------------------------------------------------------------------
# process_file — status: skipped
# ---------------------------------------------------------------------------

class TestProcessFileSkipped:
    def test_skips_when_output_newer(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt")
        out = tmp_path / "ep.corrected.srt"
        out.write_text("old corrected", encoding="utf-8")

        # Make output clearly newer than input
        future_mtime = inp.stat().st_mtime + 60
        os.utime(out, (future_mtime, future_mtime))

        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex") as mock_ex:
            status = pipeline.process_file(inp, out, "mistral", str(log))
            mock_ex.assert_not_called()

        assert status == "skipped"

    def test_log_entry_skipped(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt")
        out = tmp_path / "ep.corrected.srt"
        out.write_text("old", encoding="utf-8")
        future_mtime = inp.stat().st_mtime + 60
        os.utime(out, (future_mtime, future_mtime))
        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex"):
            pipeline.process_file(inp, out, "mistral", str(log))

        entry = json.loads(log.read_text())
        assert entry["status"] == "skipped"
        assert entry["cues_in"] is None

    def test_processes_when_output_older(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt")
        out = tmp_path / "ep.corrected.srt"
        out.write_text("stale", encoding="utf-8")

        # Make output older than input
        past_mtime = inp.stat().st_mtime - 60
        os.utime(out, (past_mtime, past_mtime))

        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(CORRECTED_SRT, _STATS_CHANGED)):
            status = pipeline.process_file(inp, out, "mistral", str(log))

        assert status == "ok"


# ---------------------------------------------------------------------------
# process_file — status: no_change
# ---------------------------------------------------------------------------

class TestProcessFileNoChange:
    def test_detected_when_hashes_match(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt", MINIMAL_SRT)
        out = tmp_path / "ep.corrected.srt"
        log = tmp_path / "pipe.log"

        # correct_srt_ex returns the same text as the input
        with patch("subtitle_pipeline.correct_srt_ex", return_value=(MINIMAL_SRT, _STATS_UNCHANGED)):
            status = pipeline.process_file(inp, out, "mistral", str(log))

        assert status == "no_change"
        assert not out.exists()  # must not write identical content

    def test_log_entry_includes_retry_hint(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt", MINIMAL_SRT)
        out = tmp_path / "ep.corrected.srt"
        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(MINIMAL_SRT, _STATS_UNCHANGED)):
            pipeline.process_file(inp, out, "mistral", str(log))

        entry = json.loads(log.read_text())
        assert entry["status"] == "no_change"
        assert "retry_with_model" in entry
        assert entry["retry_with_model"]  # non-empty

    def test_mistral_fallback_is_llama3(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt", MINIMAL_SRT)
        out = tmp_path / "ep.corrected.srt"
        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(MINIMAL_SRT, _STATS_UNCHANGED)):
            pipeline.process_file(inp, out, "mistral", str(log))

        entry = json.loads(log.read_text())
        assert entry["retry_with_model"] == "llama3"

    def test_unknown_model_fallback_is_default(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt", MINIMAL_SRT)
        out = tmp_path / "ep.corrected.srt"
        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(MINIMAL_SRT, _STATS_UNCHANGED)):
            pipeline.process_file(inp, out, "some-custom-model", str(log))

        entry = json.loads(log.read_text())
        assert entry["retry_with_model"] == pipeline._DEFAULT_FALLBACK


# ---------------------------------------------------------------------------
# process_file — status: failed
# ---------------------------------------------------------------------------

class TestProcessFileFailed:
    def test_exception_returns_failed(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt")
        out = tmp_path / "ep.corrected.srt"
        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", side_effect=RuntimeError("Ollama down")):
            status = pipeline.process_file(inp, out, "mistral", str(log))

        assert status == "failed"

    def test_log_entry_failed(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt")
        out = tmp_path / "ep.corrected.srt"
        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", side_effect=RuntimeError("Ollama down")):
            pipeline.process_file(inp, out, "mistral", str(log))

        entry = json.loads(log.read_text())
        assert entry["status"] == "failed"
        assert "Ollama down" in entry["error"]
        assert entry["cues_in"] is None

    def test_no_output_written_on_failure(self, tmp_path):
        inp = _write_srt(tmp_path / "ep.srt")
        out = tmp_path / "ep.corrected.srt"
        log = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", side_effect=RuntimeError("boom")):
            pipeline.process_file(inp, out, "mistral", str(log))

        assert not out.exists()


# ---------------------------------------------------------------------------
# run_pipeline — exit codes and summary
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def _make_files(self, tmp_path, n=1):
        files = []
        for i in range(n):
            p = tmp_path / f"ep{i}.srt"
            _write_srt(p)
            files.append(p)
        return files

    def test_exit_0_all_ok(self, tmp_path, capsys):
        files = self._make_files(tmp_path, 2)
        log = str(tmp_path / "pipe.log")

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(CORRECTED_SRT, _STATS_CHANGED)):
            code = pipeline.run_pipeline(files, tmp_path / "out", "mistral", log)

        assert code == 0
        out = capsys.readouterr().out
        assert "Pipeline complete" in out
        assert "2 ok" in out

    def test_exit_1_on_failed(self, tmp_path, capsys):
        files = self._make_files(tmp_path, 1)
        log = str(tmp_path / "pipe.log")

        with patch("subtitle_pipeline.correct_srt_ex", side_effect=RuntimeError("boom")):
            code = pipeline.run_pipeline(files, tmp_path / "out", "mistral", log)

        assert code == 1

    def test_exit_2_on_no_change(self, tmp_path, capsys):
        files = self._make_files(tmp_path, 1)
        log = str(tmp_path / "pipe.log")

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(MINIMAL_SRT, _STATS_UNCHANGED)):
            code = pipeline.run_pipeline(files, tmp_path / "out", "mistral", log)

        assert code == 2

    def test_exit_1_takes_priority_over_2(self, tmp_path):
        """When there's both a failure and a no_change, exit 1."""
        f1, f2 = self._make_files(tmp_path, 2)
        log = str(tmp_path / "pipe.log")

        effects = [RuntimeError("boom"), (MINIMAL_SRT, _STATS_UNCHANGED)]
        with patch("subtitle_pipeline.correct_srt_ex", side_effect=effects):
            code = pipeline.run_pipeline([f1, f2], tmp_path / "out", "mistral", log)

        assert code == 1

    def test_summary_printed_to_stdout(self, tmp_path, capsys):
        files = self._make_files(tmp_path, 3)
        log = str(tmp_path / "pipe.log")

        effects = [
            (CORRECTED_SRT, _STATS_CHANGED),
            (MINIMAL_SRT, _STATS_UNCHANGED),
            RuntimeError("boom"),
        ]
        with patch("subtitle_pipeline.correct_srt_ex", side_effect=effects):
            pipeline.run_pipeline(files, tmp_path / "out", "mistral", log)

        out = capsys.readouterr().out
        assert "Pipeline complete" in out
        assert "1 ok" in out
        assert "1 failed" in out
        assert "1 no_change" in out

    def test_default_output_suffix(self, tmp_path):
        """Without --output-dir, output should be {stem}.corrected.srt beside input."""
        inp = _write_srt(tmp_path / "ep.srt")
        log = str(tmp_path / "pipe.log")

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(CORRECTED_SRT, _STATS_CHANGED)):
            pipeline.run_pipeline([inp], output_dir=None, model="mistral", log_path=log)

        assert (tmp_path / "ep.corrected.srt").exists()

    def test_log_appends_multiple_entries(self, tmp_path):
        files = self._make_files(tmp_path, 2)
        log_path = tmp_path / "pipe.log"

        with patch("subtitle_pipeline.correct_srt_ex", return_value=(CORRECTED_SRT, _STATS_CHANGED)):
            pipeline.run_pipeline(files, tmp_path / "out", "mistral", str(log_path))

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            entry = json.loads(line)
            assert entry["status"] == "ok"


# ---------------------------------------------------------------------------
# _sha256 / hash helpers
# ---------------------------------------------------------------------------

class TestHashHelper:
    def test_same_text_same_hash(self):
        assert pipeline._sha256("hello") == pipeline._sha256("hello")

    def test_different_text_different_hash(self):
        assert pipeline._sha256("hello") != pipeline._sha256("world")

    def test_returns_hex_string(self):
        h = pipeline._sha256("test")
        assert isinstance(h, str)
        assert len(h) == 64
