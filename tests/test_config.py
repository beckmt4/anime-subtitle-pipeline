"""Unit tests for config.py — YAML loading, profile merging, directory creation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config import Config


def write_config(tmp_path: Path, extra: dict = None) -> Path:
    """Write a minimal test config YAML and return its path."""
    cfg = {
        "runtime": {"profile": "dev"},
        "paths": {
            "inbox": str(tmp_path / "inbox"),
            "outbox": str(tmp_path / "outbox"),
            "logs": str(tmp_path / "logs"),
            "temp": str(tmp_path / "temp"),
        },
        "asr": {
            "model_name": "test-model",
            "device": "cpu",
            "dev": {"compute_type": "int8", "beam_size": 3, "batch_size": 4},
            "prod": {"compute_type": "float16", "beam_size": 5, "batch_size": 16},
            "vad_filter": True,
            "language": "ja",
        },
        "mt": {"model_name": "test-mt", "device": "cpu", "batch_size": 8, "max_length": 256},
        "llm": {
            "enabled": False,
            "base_url": "http://localhost:11434",
            "dev": {"model_name": "test-llm"},
            "prod": {"model_name": "test-llm"},
            "style": "natural",
            "max_lines": 2,
            "max_chars_per_line": 42,
            "timeout": 30,
            "temperature": 0.3,
            "prompts": {
                "natural": "You are a test polisher. Max {max_lines} lines, {max_chars_per_line} chars.",
                "literal": "You are literal.",
            },
        },
        "subtitles": {"min_duration_sec": 0.5, "max_duration_sec": 7.0},
        "mux": {"enabled": False, "output_suffix": "en"},
        "logging": {"level": "INFO"},
        "generate": {
            "prefer_subtitles": True,
            "prefer_audio_language": "auto",
            "use_llm_polish": False,
        },
    }
    if extra:
        cfg.update(extra)
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Basic loading
# ---------------------------------------------------------------------------

class TestConfigLoad:
    def test_loads_without_error(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        assert cfg is not None

    def test_raises_file_not_found_for_missing_config(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Config(str(tmp_path / "nonexistent.yaml"))

    def test_default_profile_from_yaml(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        assert cfg.profile == "dev"

    def test_get_nested_key(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        assert cfg.get("asr", "model_name") == "test-model"

    def test_get_returns_default_for_missing_key(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        assert cfg.get("nonexistent", "key", default="fallback") == "fallback"

    def test_get_returns_none_default_when_no_default_given(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        assert cfg.get("nonexistent") is None


# ---------------------------------------------------------------------------
# Directory creation
# ---------------------------------------------------------------------------

class TestDirectoryCreation:
    def test_creates_inbox_outbox_logs_temp(self, tmp_path):
        p = write_config(tmp_path)
        Config(str(p))
        for name in ("inbox", "outbox", "logs", "temp"):
            assert (tmp_path / name).is_dir(), f"{name} was not created"

    def test_idempotent_when_dirs_already_exist(self, tmp_path):
        p = write_config(tmp_path)
        Config(str(p))
        # Second load must not raise even though dirs already exist
        Config(str(p))


# ---------------------------------------------------------------------------
# Profile override
# ---------------------------------------------------------------------------

class TestProfileOverride:
    def test_dev_profile_uses_dev_settings(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p), profile_override="dev")
        assert cfg.profile == "dev"
        assert cfg.asr_compute_type == "int8"
        assert cfg.asr_batch_size == 4

    def test_prod_profile_uses_prod_settings(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p), profile_override="prod")
        assert cfg.profile == "prod"
        assert cfg.asr_compute_type == "float16"
        assert cfg.asr_batch_size == 16

    def test_profile_override_takes_precedence_over_yaml(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p), profile_override="prod")
        assert cfg.profile == "prod"


# ---------------------------------------------------------------------------
# Property accessors
# ---------------------------------------------------------------------------

class TestConfigProperties:
    def test_llm_enabled(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        assert cfg.llm_enabled is False

    def test_asr_language_is_ja(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        assert cfg.asr_language == "ja"

    def test_subtitle_min_duration(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        assert cfg.subtitle_min_duration == pytest.approx(0.5)

    def test_subtitle_max_duration(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        assert cfg.subtitle_max_duration == pytest.approx(7.0)

    def test_get_llm_prompt_fills_placeholders(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        prompt = cfg.get_llm_prompt("natural")
        assert "2" in prompt    # max_lines
        assert "42" in prompt   # max_chars_per_line

    def test_asr_device_returns_cpu_when_set_to_cpu(self, tmp_path):
        p = write_config(tmp_path)
        cfg = Config(str(p))
        # config sets device: cpu — no torch import triggered
        assert cfg.asr_device == "cpu"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def write_config_relative_paths(config_file: Path) -> None:
    """Write a minimal config with relative paths sections."""
    cfg = {
        "runtime": {"profile": "dev"},
        "paths": {
            "inbox": "./inbox",
            "outbox": "./outbox",
            "logs": "./logs",
            "temp": "./temp",
        },
    }
    config_file.write_text(yaml.dump(cfg), encoding="utf-8")


class TestGetPathResolution:
    def test_relative_path_resolves_to_config_dir(self, tmp_path):
        """Relative paths resolve relative to the config file, not the cwd."""
        nested = tmp_path / "project" / "configs"
        nested.mkdir(parents=True)
        config_file = nested / "config.yaml"
        write_config_relative_paths(config_file)

        cfg = Config(str(config_file))
        assert cfg.get_path("outbox") == str(nested / "outbox")

    def test_absolute_path_returned_unchanged(self, tmp_path):
        """Absolute paths in config are returned as-is."""
        abs_outbox = str(tmp_path / "absolute" / "outbox")
        # Use the standard helper but override the outbox to an absolute path
        extra = {"paths": {
            "inbox": str(tmp_path / "inbox"),
            "outbox": abs_outbox,
            "logs": str(tmp_path / "logs"),
            "temp": str(tmp_path / "temp"),
        }}
        config_file = write_config(tmp_path, extra=extra)

        cfg = Config(str(config_file))
        assert cfg.get_path("outbox") == abs_outbox

    def test_cwd_independent_resolution(self, tmp_path, monkeypatch):
        """Path resolution must not depend on the process cwd."""
        nested = tmp_path / "project"
        nested.mkdir()
        config_file = nested / "config.yaml"
        write_config_relative_paths(config_file)

        # Change the cwd to somewhere completely different
        monkeypatch.chdir(tmp_path)

        cfg = Config(str(config_file))
        assert cfg.get_path("inbox") == str(nested / "inbox")
        assert cfg.get_path("logs") == str(nested / "logs")

    def test_directories_created_relative_to_config_dir(self, tmp_path):
        """_ensure_directories should create dirs relative to the config file."""
        nested = tmp_path / "project" / "configs"
        nested.mkdir(parents=True)
        config_file = nested / "config.yaml"
        write_config_relative_paths(config_file)

        Config(str(config_file))
        for name in ("inbox", "outbox", "logs", "temp"):
            assert (nested / name).is_dir(), f"{name} was not created under config dir"


# ---------------------------------------------------------------------------
# Default config — generate key placement regression guard
# ---------------------------------------------------------------------------

class TestDefaultConfigGeneratePlacement:
    """Guard against the regression where generate: was nested under benchmark:.

    When generate: is mis-placed, cfg.get('generate', ...) silently returns
    None (the default) instead of the configured value.  Loading the real
    config.yaml ensures the key stays at the top level.
    """

    @pytest.fixture
    def default_cfg(self):
        default_config = Path(__file__).parent.parent / "config.yaml"
        return Config(str(default_config))

    def test_prefer_subtitles_is_not_none(self, default_cfg):
        assert default_cfg.get("generate", "prefer_subtitles") is not None

    def test_prefer_audio_language_is_not_none(self, default_cfg):
        assert default_cfg.get("generate", "prefer_audio_language") is not None

    def test_use_llm_polish_is_not_none(self, default_cfg):
        assert default_cfg.get("generate", "use_llm_polish") is not None
