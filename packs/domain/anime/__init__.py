"""packs.domain.anime — Anime and animated series domain pack.

Supplies anime-specific style, glossary, and review configuration that
``core`` modules accept as injectable parameters.

Modules
-------
style       Honorific handling, OP/ED treatment, on-screen text policy.
glossary    Common anime terminology overrides (loaded from glossary.yaml).

Pack metadata
-------------
DOMAIN_ID = "anime"
"""

from __future__ import annotations

DOMAIN_ID: str = "anime"

__all__ = ["DOMAIN_ID"]
