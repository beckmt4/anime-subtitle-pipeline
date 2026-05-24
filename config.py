"""Compatibility shim for the migrated runtime config module."""

from __future__ import annotations

import sys

from core.runtime import config as _config

sys.modules[__name__] = _config
