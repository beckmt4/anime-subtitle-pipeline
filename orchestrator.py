"""Compatibility shim for the migrated runtime orchestrator module."""

from __future__ import annotations

import sys

from core.runtime import orchestrator as _orchestrator

sys.modules[__name__] = _orchestrator
