"""Compatibility shim for the migrated runtime batch processing module."""

from __future__ import annotations

import sys

from core.runtime import batch_process as _batch_process

if __name__ == "__main__":
    _batch_process.main()
else:
    sys.modules[__name__] = _batch_process
