"""packs.domain.jav — JAV domain pack.

Supplies JAV-specific privacy, content gating, and logging redaction that
``core`` modules accept as injectable parameters.

**Adult content opt-in is required.**  This pack is disabled by default and
must be explicitly enabled in the runtime configuration:

    domain:
      pack: jav
      adult_content_opt_in: true

Modules
-------
privacy     Logging redaction and content gate enforcement.

Pack metadata
-------------
DOMAIN_ID         = "jav"
REQUIRES_OPT_IN   = True
"""

from __future__ import annotations

DOMAIN_ID: str = "jav"
REQUIRES_OPT_IN: bool = True

__all__ = ["DOMAIN_ID", "REQUIRES_OPT_IN"]
