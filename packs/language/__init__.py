"""packs.language — language pack sub-packages.

A language pack covers exactly one source→target translation direction.
It supplies:

- Language tag alias normalisation (ISO-639 variants → canonical code).
- LLM prompt templates (system prompt + per-segment prompt skeleton).
- Language-specific post-processing hooks (e.g. CJK leak remediation).
- Model defaults (preferred ASR model, preferred MT model).
- Quality thresholds specific to this language pair.

Available packs
---------------
ja_en   Japanese source → English target.
"""
