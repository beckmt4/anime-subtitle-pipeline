"""Subtitle Intelligence Platform — core package.

The ``core`` package contains all language-agnostic, domain-agnostic platform
capabilities.  Nothing in this tree may hardcode Japanese, English, anime, JAV,
or any other language/domain assumption — those belong in ``packs/``.

Sub-packages
------------
media       stream inspection and source discovery
extract     audio extraction, subtitle demux and mux
ocr         bitmap subtitle → text (not yet implemented)
asr         speech → text backend abstraction
mt          translation backend abstraction
polish      LLM quality improvement backend
subtitles   Segment / SubtitleCandidate data model and SRT formatting
benchmark   candidate comparison and quality metrics
artifacts   processing ledger and artifact storage (Issue #18)
policy      quality threshold routing decisions
review      review task model and queue (Issue #22)
runtime     config, orchestration, CLI entry point, tracing
"""
