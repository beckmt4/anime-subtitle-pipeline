"""
Configuration loader and manager.

This module handles loading and validating the config.yaml file,
applying profile-specific settings, and providing typed access to
configuration values throughout the application.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        for section in ("asr", "llm", "mt", "mux", "generate", "qc"):
            if section in self._config:
                profile_overrides = self._config[section].get(self.profile, {})
                self._config[section].update(profile_overrides)
                for key in self._PROFILE_KEYS:
                    self._config[section].pop(key, None)
    
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

    @property
    def domain_pack(self) -> Optional[str]:
        """Return active domain pack ID from explicit config or policy fallback."""
        explicit_pack = self.get("packs", "domain", default=None)
        if explicit_pack in {"anime", "jav"}:
            return explicit_pack
        explicit = self.get("domain", "pack", default=None)
        if explicit in {"anime", "jav"}:
            return explicit
        auto_select_anime = bool(
            self.get("domain", "policy", "auto_select_anime_for_ja_content", default=False)
        )
        if not auto_select_anime:
            return None
        preferred_audio = str(
            self.get("generate", "prefer_audio_language", default="auto")
        ).lower()
        asr_lang = str(self.get("asr", "language", default="ja")).lower()
        if asr_lang == "ja" and preferred_audio in {"auto", "ja"}:
            return "anime"
        return None

    def get_domain_style_config(self) -> Dict[str, Any]:
        """Return active domain style config (or empty dict when not configured)."""
        if self.domain_pack == "anime":
            from packs.domain.anime.style import get_style_config
            return get_style_config()
        if self.domain_pack == "jav":
            from packs.domain.jav.style import get_style_config
            return get_style_config()
        return {}

    def get_domain_glossary_terms(self) -> List[Dict[str, str]]:
        """Return active domain glossary terms with config override support."""
        if self.domain_pack != "anime":
            return []
        from packs.domain.anime.glossary import load_glossary_terms
        glossary_path = self.get("domain", "anime", "glossary_path", default=None)
        overrides = self.get("domain", "anime", "glossary_overrides", default=[])
        return load_glossary_terms(glossary_path=glossary_path, overrides=overrides)
    
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
    def translation_engine(self) -> str:
        return self.get("translation", "engine", default="marian")

    @property
    def translation_fallback_engine(self) -> str:
        return self.get("translation", "fallback_engine", default="marian")

    @property
    def translation_context_window_segments(self) -> int:
        return self.get("translation", "context_window_segments", default=4)

    @property
    def translation_mode(self) -> str:
        return self.get("translation", "mode", default="accuracy_first")

    @property
    def translation_dialogue_profile(self) -> str:
        return self.get("translation", "dialogue_profile", default="default")

    @property
    def translation_workflow(self) -> str:
        return self.get("translation", "workflow", default="single_pass")

    @property
    def translation_save_intermediate(self) -> bool:
        return bool(self.get("translation", "save_intermediate", default=False))
    
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
    def domain_adult_content_opt_in(self) -> bool:
        return bool(self.get("domain", "adult_content_opt_in", default=False))
    
    @property
    def llm_style(self) -> str:
        domain_style = self.get_domain_style_config().get("llm_style")
        if isinstance(domain_style, str) and domain_style:
            return domain_style
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
        if not prompt_template and style in {"anime_natural", "jav_conversational"}:
            prompt_template = self.get("llm", "prompts", "natural", default="")
        
        try:
            prompt = prompt_template.format(
                max_lines=self.llm_max_lines,
                max_chars_per_line=self.llm_max_chars_per_line,
            )
            if self.domain_pack == "anime":
                domain_style = self.get_domain_style_config()
                domain_lines = ["Anime domain policy:"]
                if domain_style.get("preserve_honorifics"):
                    domain_lines.append(
                        "- Preserve Japanese honorifics (e.g., san/kun/chan/senpai/sensei)."
                    )
                if domain_style.get("skip_op_ed_segments"):
                    domain_lines.append(
                        "- For OP/ED lyrics, preserve intent and avoid creative rewrites."
                    )
                if domain_style.get("translate_on_screen_text"):
                    domain_lines.append(
                        "- Translate plot-relevant signs and on-screen text naturally."
                    )
                terms = self.get_domain_glossary_terms()
                if terms:
                    domain_lines.append("- Preferred glossary translations:")
                    domain_lines.extend(
                        f"  - {term['source']} -> {term['target']}"
                        for term in terms
                    )
                prompt = f"{prompt}\n\n" + "\n".join(domain_lines)
            elif self.domain_pack == "jav":
                domain_style = self.get_domain_style_config()
                domain_lines = ["JAV domain policy:"]
                if domain_style.get("dialogue_profile") == "live_action_adult":
                    domain_lines.append(
                        "- Use the live_action_adult dialogue profile for direct conversational speech."
                    )
                if domain_style.get("preserve_adult_register"):
                    domain_lines.append(
                        "- Preserve explicit/adult register when present; do not euphemize or sanitize."
                    )
                if self.get("domain", "jav", "privacy", "redact_reports", default=False):
                    domain_lines.append(
                        "- Treat filenames and local paths as sensitive; use redacted labels in reports."
                    )
                if domain_style.get("review_mode"):
                    domain_lines.append(f"- Review mode: {domain_style['review_mode']}.")
                prompt = f"{prompt}\n\n" + "\n".join(domain_lines)
            return prompt
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(
                f"LLM prompt template for style '{style}' has an unexpected placeholder: {exc}. "
                f"Only {{max_lines}} and {{max_chars_per_line}} are supported."
            ) from exc
    
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
