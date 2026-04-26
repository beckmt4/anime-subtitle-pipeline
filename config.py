"""
Configuration loader and manager.

This module handles loading and validating the config.yaml file,
applying profile-specific settings, and providing typed access to
configuration values throughout the application.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


# Environment variable overrides — set these in docker-compose or shell to
# avoid editing config.yaml per deployment.
#   LLM_BASE_URL  — Ollama endpoint (e.g. http://192.168.1.147:11434 for Unraid)


class Config:
    """
    Central configuration manager.
    
    Loads config.yaml and applies profile-specific settings (dev vs prod).
    Provides convenient access to all configuration parameters.
    """
    
    def __init__(self, config_path: str = "config.yaml", profile_override: Optional[str] = None):
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to config.yaml file
            profile_override: Override the profile from CLI (e.g., "dev" or "prod")
        """
        self.config_path = Path(config_path).resolve()
        
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config: Dict[str, Any] = yaml.safe_load(f)
        
        # Determine active profile
        self.profile = profile_override or self._config.get("runtime", {}).get("profile", "dev")
        
        # Apply profile-specific settings
        self._apply_profile()
        
        # Create directories if they don't exist
        self._ensure_directories()
    
    # Known profile sub-dict keys that are removed after merging.
    _PROFILE_KEYS = ("dev", "prod")

    def _apply_profile(self) -> None:
        """
        Apply profile-specific settings to the active configuration.
        
        Merges profile-specific settings (dev/prod) into the main configuration
        dictionary, overwriting base settings with profile-specific values.
        Profile sub-dicts are removed after merging so that subsequent calls to
        ``get()`` never accidentally return a nested dict.
        """
        # ASR profile settings
        if "asr" in self._config:
            asr_profile = self._config["asr"].get(self.profile, {})
            self._config["asr"].update(asr_profile)
            for key in self._PROFILE_KEYS:
                self._config["asr"].pop(key, None)
        
        # LLM profile settings
        if "llm" in self._config:
            llm_profile = self._config["llm"].get(self.profile, {})
            self._config["llm"].update(llm_profile)
            for key in self._PROFILE_KEYS:
                self._config["llm"].pop(key, None)
    
    def _ensure_directories(self) -> None:
        """
        Create necessary directories if they don't exist.
        
        Creates inbox, outbox, logs, and temp directories as specified in the
        configuration file. Uses parents=True to create parent directories.
        """
        for path_key in ["inbox", "outbox", "logs", "temp"]:
            path = Path(self.get_path(path_key))
            path.mkdir(parents=True, exist_ok=True)
    
    def get(self, *keys: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.
        
        Args:
            *keys: Sequence of keys to traverse (e.g., "asr", "model_name")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        value = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value
    
    def get_path(self, path_name: str) -> str:
        """Get an absolute path from the paths section.

        Relative paths are resolved relative to the directory containing the
        loaded config file, so behaviour is independent of the process cwd.
        Absolute paths are returned unchanged.
        """
        rel_path = self.get("paths", path_name, default=".")
        p = Path(rel_path)
        if p.is_absolute():
            return str(p)
        return str((self.config_path.parent / p).resolve())
    
    # Convenient property accessors for common settings
    
    @property
    def asr_model_name(self) -> str:
        return self.get("asr", "model_name", default="large-v3-turbo")
    
    @property
    def asr_device(self) -> str:
        device = self.get("asr", "device", default="auto")
        if device == "auto":
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device
    
    @property
    def asr_compute_type(self) -> str:
        return self.get("asr", "compute_type", default="int8_float16")
    
    @property
    def asr_batch_size(self) -> int:
        return self.get("asr", "batch_size", default=8)
    
    @property
    def asr_beam_size(self) -> int:
        return self.get("asr", "beam_size", default=5)
    
    @property
    def asr_vad_filter(self) -> bool:
        return self.get("asr", "vad_filter", default=True)
    
    @property
    def asr_language(self) -> str:
        return self.get("asr", "language", default="ja")
    
    @property
    def mt_model_name(self) -> str:
        return self.get("mt", "model_name", default="Helsinki-NLP/opus-mt-ja-en")
    
    @property
    def mt_device(self) -> str:
        return self.get("mt", "device", default="cpu")
    
    @property
    def mt_batch_size(self) -> int:
        return self.get("mt", "batch_size", default=16)
    
    @property
    def llm_enabled(self) -> bool:
        return self.get("llm", "enabled", default=True)
    
    @property
    def llm_base_url(self) -> str:
        return os.environ.get("LLM_BASE_URL") or self.get("llm", "base_url", default="http://localhost:11434")
    
    @property
    def llm_model_name(self) -> str:
        return self.get("llm", "model_name", default="qwen2.5:7b")
    
    @property
    def llm_style(self) -> str:
        return self.get("llm", "style", default="natural")
    
    @property
    def llm_max_lines(self) -> int:
        return self.get("llm", "max_lines", default=2)
    
    @property
    def llm_max_chars_per_line(self) -> int:
        return self.get("llm", "max_chars_per_line", default=42)
    
    @property
    def llm_temperature(self) -> float:
        return self.get("llm", "temperature", default=0.3)
    
    @property
    def llm_timeout(self) -> int:
        return self.get("llm", "timeout", default=30)
    
    @property
    def mux_enabled(self) -> bool:
        return self.get("mux", "enabled", default=False)
    
    @property
    def mux_output_suffix(self) -> str:
        return self.get("mux", "output_suffix", default="en")
    
    @property
    def subtitle_min_duration(self) -> float:
        return self.get("subtitles", "min_duration_sec", default=0.5)
    
    @property
    def subtitle_max_duration(self) -> float:
        return self.get("subtitles", "max_duration_sec", default=7.0)

    @property
    def qc_max_cps(self) -> float:
        """Maximum reading speed in characters per second for QC validation."""
        return self.get("qc", "max_cps", default=20.0)
    
    @property
    def log_level(self) -> str:
        return self.get("logging", "level", default="INFO")

    @property
    def artifacts_db_path(self) -> str:
        """Path to the SQLite artifact registry database.

        Resolution order:
        1. artifacts.db_path in config.yaml (if non-empty)
        2. <outbox>/pipeline.db (auto-derived from paths.outbox)
        """
        configured = self.get("artifacts", "db_path", default="")
        if configured:
            return configured
        return str(Path(self.get_path("outbox")) / "pipeline.db")
    
    def get_llm_prompt(self, style: Optional[str] = None) -> str:
        """
        Get the LLM system prompt for the specified style.
        
        Args:
            style: "natural" or "literal", defaults to config setting
            
        Returns:
            Formatted system prompt
        """
        style = style or self.llm_style
        prompt_template = self.get("llm", "prompts", style, default="")
        
        # Fill in formatting placeholders
        return prompt_template.format(
            max_lines=self.llm_max_lines,
            max_chars_per_line=self.llm_max_chars_per_line
        )
    
    def __repr__(self) -> str:
        return f"Config(profile={self.profile}, config_path={self.config_path})"


# Global config instance (initialized in main.py)
_global_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    if _global_config is None:
        raise RuntimeError("Configuration not initialized. Call set_config() first.")
    return _global_config


def set_config(config: Config) -> None:
    """
    Set the global configuration instance.
    
    Args:
        config: Configuration object to set as global
    """
    global _global_config
    _global_config = config
