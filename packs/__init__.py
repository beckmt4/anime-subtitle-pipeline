"""Subtitle Intelligence Platform — packs package.

Packs supply language-specific or domain-specific configuration, prompts,
preprocessing hooks, and quality thresholds that core modules accept as
injectable parameters.

Sub-packages
------------
language/   Language packs.  Each sub-package is named by its
            source_lang-target_lang direction (e.g. ``ja_en``).
domain/     Domain packs.  Each sub-package is named by domain
            (e.g. ``anime``, ``jav``).

Core modules must never import from ``packs/`` directly.  Packs are loaded
by ``core.runtime`` and injected as parameters into capability modules.
"""
