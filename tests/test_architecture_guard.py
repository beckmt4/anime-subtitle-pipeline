"""
Architecture guard tests.

These tests enforce structural contracts across the codebase to prevent
regressions as the repo evolves with AI-assisted development:

1. docs/FILE_OVERVIEW.md must not reference deleted root shims as active modules.
2. docs/PROJECT_SUMMARY.md must not reference deleted root shims.
3. No code in core/ or packs/ imports from deleted root shims.
4. acceptance/acceptance-test-index.md references every acceptance/*.md file.

Hardcoded-language guards (no "Japanese dialogue into English subtitles" in
core/mt/__init__.py) are defined here as skipped stubs pending Epic 07 Task C.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Root-level shim names that have been retired to attic/ and must not be
# referenced as importable modules in docs or imported from core/packs.
DELETED_ROOT_SHIMS = {
    "config",          # → core.runtime.config
    "audio_utils",     # → core.extract.audio_utils
    "asr",             # → core.asr
    "mt",              # → core.mt
    "llm_polish",      # → core.polish
    "srt_writer",      # → core.subtitles
    "media_inspect",   # → core.media
    "subtitle_utils",  # → core.extract.subtitle_utils
}

# Import patterns that indicate a root-shim import
_IMPORT_PATTERNS = [
    re.compile(r"^from\s+(" + "|".join(DELETED_ROOT_SHIMS) + r")\s+import", re.MULTILINE),
    re.compile(r"^import\s+(" + "|".join(DELETED_ROOT_SHIMS) + r")\b", re.MULTILINE),
]

# Phrases that indicate a stale docs reference to root shims as active code
_STALE_DOC_PATTERNS = [
    # Matches lines describing old root shim files as "Core Pipeline Files"
    re.compile(r"Core Pipeline Files.*\(7\)", re.IGNORECASE),
    # Matches a file structure listing root shim files as first-class modules
    re.compile(r"├── (config|audio_utils|asr|mt|llm_polish|srt_writer)\.py\s+#\s+\w"),
    # Matches old-style API examples that import root shims
    re.compile(r"from (config|audio_utils|asr|mt|llm_polish|srt_writer) import"),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _collect_python_files(directory: Path) -> list:
    return [p for p in directory.rglob("*.py") if "__pycache__" not in str(p)]


# ---------------------------------------------------------------------------
# Doc freshness guards
# ---------------------------------------------------------------------------

class TestFileOverviewFreshness:
    """docs/FILE_OVERVIEW.md must not contain stale root-shim references."""

    def _read(self):
        path = REPO_ROOT / "docs" / "FILE_OVERVIEW.md"
        assert path.exists(), "docs/FILE_OVERVIEW.md is missing"
        return path.read_text(encoding="utf-8")

    def test_no_stale_core_pipeline_files_heading(self):
        """Must not claim '17 total' old root files as the file list."""
        content = self._read()
        assert "Core Pipeline Files (7)" not in content, (
            "docs/FILE_OVERVIEW.md still references the stale '7 Core Pipeline Files' "
            "section from the original flat-file layout."
        )

    def test_no_root_shim_as_active_module(self):
        """Must not list config.py / audio_utils.py / asr.py etc. as active modules."""
        content = self._read()
        for shim in ("config.py", "audio_utils.py", "asr.py", "mt.py",
                     "llm_polish.py", "srt_writer.py"):
            # Allow mentions in the attic/ context or in notes about what was retired,
            # but not as first-class module entries in a file tree
            bad_pattern = re.compile(
                r"├──\s+" + re.escape(shim) + r"\s+#",
                re.MULTILINE,
            )
            assert not bad_pattern.search(content), (
                f"docs/FILE_OVERVIEW.md still lists '{shim}' as an active root module "
                f"in a directory tree. This file has been retired to attic/."
            )

    def test_no_stale_import_example(self):
        """Must not contain import examples using deleted root shims."""
        content = self._read()
        for shim in DELETED_ROOT_SHIMS:
            bad = f"from {shim} import"
            assert bad not in content, (
                f"docs/FILE_OVERVIEW.md contains a stale import example: "
                f"'from {shim} import'. Update to 'from core.* import'."
            )


class TestProjectSummaryFreshness:
    """docs/PROJECT_SUMMARY.md must not contain stale root-shim references."""

    def _read(self):
        path = REPO_ROOT / "docs" / "PROJECT_SUMMARY.md"
        assert path.exists(), "docs/PROJECT_SUMMARY.md is missing"
        return path.read_text(encoding="utf-8")

    def test_no_stale_file_structure_listing(self):
        """Must not list root shims in the main file structure tree."""
        content = self._read()
        for shim in ("audio_utils.py", "asr.py", "mt.py", "llm_polish.py",
                     "srt_writer.py"):
            bad_pattern = re.compile(
                r"├──\s+" + re.escape(shim) + r"\s+#",
                re.MULTILINE,
            )
            assert not bad_pattern.search(content), (
                f"docs/PROJECT_SUMMARY.md still lists '{shim}' as an active root "
                f"file. This has been migrated to core/."
            )

    def test_no_stale_api_import_example(self):
        """API usage examples must import from core.*, not root shims."""
        content = self._read()
        for shim in DELETED_ROOT_SHIMS:
            bad = f"from {shim} import"
            assert bad not in content, (
                f"docs/PROJECT_SUMMARY.md contains a stale API example: "
                f"'from {shim} import'. Update to 'from core.* import'."
            )

    def test_references_product_readiness_doc(self):
        """Must reference the product-readiness doc now that it exists."""
        content = self._read()
        assert "product-readiness" in content, (
            "docs/PROJECT_SUMMARY.md should reference docs/product-readiness.md "
            "so readers know where to find feature status."
        )


# ---------------------------------------------------------------------------
# Import guards: core/ and packs/ must not import deleted root shims
# ---------------------------------------------------------------------------

class TestNoCoreImportsRootShims:
    """core/ modules must import from core.* not from deleted root shims."""

    def _python_files(self):
        return _collect_python_files(REPO_ROOT / "core")

    def test_no_shim_imports_in_core(self):
        violations = []
        for path in self._python_files():
            source = path.read_text(encoding="utf-8", errors="replace")
            for pat in _IMPORT_PATTERNS:
                for m in pat.finditer(source):
                    rel = path.relative_to(REPO_ROOT)
                    violations.append(f"{rel}: {m.group(0).strip()!r}")
        assert not violations, (
            "core/ contains imports from deleted root shims:\n"
            + "\n".join(f"  {v}" for v in violations)
        )


class TestNoPacksImportsRootShims:
    """packs/ modules must import from core.* not from deleted root shims."""

    def _python_files(self):
        return _collect_python_files(REPO_ROOT / "packs")

    def test_no_shim_imports_in_packs(self):
        violations = []
        for path in self._python_files():
            source = path.read_text(encoding="utf-8", errors="replace")
            for pat in _IMPORT_PATTERNS:
                for m in pat.finditer(source):
                    rel = path.relative_to(REPO_ROOT)
                    violations.append(f"{rel}: {m.group(0).strip()!r}")
        assert not violations, (
            "packs/ contains imports from deleted root shims:\n"
            + "\n".join(f"  {v}" for v in violations)
        )


# ---------------------------------------------------------------------------
# Acceptance-test index completeness guard
# ---------------------------------------------------------------------------

class TestAcceptanceIndexCompleteness:
    """Every acceptance/*.md file must appear in acceptance/acceptance-test-index.md."""

    def test_all_acceptance_files_indexed(self):
        acceptance_dir = REPO_ROOT / "acceptance"
        index_path = acceptance_dir / "acceptance-test-index.md"

        if not index_path.exists():
            # Index not yet created — skip rather than fail so CI doesn't
            # break before the index is added.
            import pytest
            pytest.skip("acceptance/acceptance-test-index.md does not exist yet")

        index_content = index_path.read_text(encoding="utf-8")

        acceptance_files = [
            p.name for p in acceptance_dir.glob("*.md")
            if p.name != "acceptance-test-index.md" and p.name != "README.md"
        ]

        missing = [
            name for name in acceptance_files
            if name not in index_content
        ]

        assert not missing, (
            "The following acceptance/*.md files are not referenced in "
            "acceptance/acceptance-test-index.md:\n"
            + "\n".join(f"  {m}" for m in sorted(missing))
            + "\nUpdate acceptance/acceptance-test-index.md to include them."
        )


# ---------------------------------------------------------------------------
# Hardcoded-language guards (pending Epic 07 Task C)
# ---------------------------------------------------------------------------

class TestNoHardcodedJaEnInCoreMt:
    """
    core/mt/__init__.py must not contain hardcoded Japanese/English prompt strings.

    These tests are currently skipped pending Epic 07 Task C
    (specs/epics/epic-07-multi-language-proof.md).  Unskip when that task lands.
    """

    def test_no_hardcoded_japanese_system_prompt(self):
        import pytest
        pytest.skip(
            "Pending Epic 07 Task C: generalize LLMDirectTranslator prompts. "
            "See specs/epics/epic-07-multi-language-proof.md"
        )
        path = REPO_ROOT / "core" / "mt" / "__init__.py"
        content = path.read_text(encoding="utf-8")
        assert "You are translating Japanese dialogue into English subtitles" not in content, (
            "core/mt/__init__.py contains a hardcoded Japanese→English system prompt. "
            "Move this to packs/language/ja_en/prompts.py and use the language-pack "
            "hook instead. See specs/epics/epic-07-multi-language-proof.md Task C."
        )

    def test_no_source_text_ja_meta_key(self):
        import pytest
        pytest.skip(
            "Pending Epic 07 Task C: rename source_text_ja to language-agnostic key. "
            "See specs/epics/epic-07-multi-language-proof.md"
        )
        path = REPO_ROOT / "core" / "mt" / "__init__.py"
        content = path.read_text(encoding="utf-8")
        assert '"source_text_ja"' not in content, (
            'core/mt/__init__.py uses "source_text_ja" as a meta key, '
            "which hardcodes the source language. "
            "Rename to 'source_text' or 'source_text_{source_lang}'. "
            "See specs/epics/epic-07-multi-language-proof.md Task C."
        )
