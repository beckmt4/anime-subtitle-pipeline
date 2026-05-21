"""JAV-specific subtitle style policy."""

from __future__ import annotations

from typing import Any, Dict

_DEFAULT_STYLE: Dict[str, Any] = {
    "max_chars_per_line": 44,
    "max_lines_per_segment": 2,
    "llm_style": "jav_conversational",
    "dialogue_profile": "live_action_adult",
    "preserve_adult_register": True,
    "flag_low_confidence": True,
    "flag_high_risk_content": True,
    "review_mode": "adult",
    "conversation_tone": "direct_conversational",
}


def get_style_config() -> Dict[str, Any]:
    """Return the default JAV domain style configuration dict."""
    return dict(_DEFAULT_STYLE)


__all__ = ["get_style_config"]
