"""core.artifacts.pipeline_wiring -- helpers for wiring ArtifactRegistry into the pipeline.

Provides two public functions consumed by main.py and orchestrator.py:

    compute_media_hash(path)  -- SHA-256 hex digest of any file, read in chunks.
    open_registry(cfg)        -- Open (or create) the registry DB from config;
                                 returns None and logs a warning on any failure.

Design rules
------------
* Registry failures must never crash the pipeline.  Every public function here
  either returns a value or returns None — it never raises.
* The DB path is resolved from config (artifacts.db_path) with a fallback of
  <outbox>/pipeline.db so the registry works out-of-the-box with zero config.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Read files in 1 MiB chunks when hashing to keep memory use flat for large
# video files.
_HASH_CHUNK_BYTES = 1 << 20  # 1 MiB


def compute_media_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of *path*, read in 1 MiB chunks.

    Args:
        path: Filesystem path to the file to hash.

    Returns:
        64-character lowercase hex string.

    Raises:
        OSError: if the file cannot be opened or read.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def open_registry(cfg) -> Optional["ArtifactRegistry"]:  # noqa: F821  (forward ref)
    """Open (or create) the artifact registry database described by *cfg*.

    Resolution order for the DB path:
    1. ``artifacts.db_path`` in config.yaml (if non-empty).
    2. ``<paths.outbox>/pipeline.db`` (auto-derived).

    Returns:
        An open :class:`~core.artifacts.ArtifactRegistry`, or ``None`` if the
        DB path cannot be determined or the database fails to initialise.
        Callers **must** handle ``None`` gracefully so the pipeline continues
        even when the registry is unavailable (e.g., read-only filesystem,
        missing outbox directory).
    """
    # Import here to avoid circular imports at module load time.
    from core.artifacts import ArtifactRegistry

    try:
        db_path = cfg.artifacts_db_path
    except Exception as exc:
        logger.warning(
            "ArtifactRegistry: could not determine db_path from config — "
            "registry disabled: %s", exc,
        )
        return None

    try:
        # Ensure the parent directory exists (outbox may not yet be created).
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        registry = ArtifactRegistry(db_path)
        logger.info("ArtifactRegistry opened: %s", db_path)
        return registry
    except Exception as exc:
        logger.warning(
            "ArtifactRegistry: failed to open %s — registry disabled: %s",
            db_path, exc,
        )
        return None


__all__ = ["compute_media_hash", "open_registry"]
