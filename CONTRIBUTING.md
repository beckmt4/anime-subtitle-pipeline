# Contributing to anime-subtitle-pipeline

This project is a local-first subtitle intelligence platform. It uses AI tools heavily for development. This guide defines how contributions work — for humans and AI tools alike.

Related: [docs/ai-dev-policy.md](docs/ai-dev-policy.md) covers AI-specific rules in more detail.

---

## Merge gate — non-negotiable

**No change merges without:**
1. Tests that cover the new or changed behavior (or an explicit, documented reason why none apply).
2. A completed acceptance checklist in the PR — either referencing an `acceptance/` doc or filled inline in the PR template.
3. Human review of any AI-generated code.

This applies to all contributors, human and AI.

---

## Contribution workflow

### For a feature or fix

1. Open or reference an issue before starting significant work.
2. Check `specs/` for an existing spec. If none exists and the change is non-trivial, write one first.
3. Write or update tests before or alongside code changes — not after.
4. Fill out the PR template fully. Every section. No skipped checkboxes without explanation.
5. If you used AI tooling to generate code, say so in the AI usage disclosure section of the PR.
6. A human must review the diff and approve before merge. AI-authored reviews do not count as human approval.

### For documentation or architecture work

1. Docs live in `docs/`. Architecture notes go in `docs/architecture/`.
2. If the doc is the primary deliverable of an issue, the acceptance criteria from that issue must be mapped explicitly in the doc (see `docs/architecture/module-boundaries.md` as the reference example).
3. No merge gate for pure doc changes, but a PR is still required for anything in `docs/`.

### For AI-assisted sessions (Claude Code, ChatGPT, Gemini, etc.)

Follow [docs/ai-dev-policy.md](docs/ai-dev-policy.md). Key points:
- AI-generated code must be read and validated before committing.
- Do not commit AI output that you have not run or reviewed.
- If the AI makes an assumption that changes scope or design, document it.
- Prompts used for significant implementation work go in `prompts/` for reproducibility.

---

## Branch and PR conventions

### Branch names

```
feature/short-description
fix/short-description
docs/short-description
refactor/short-description
chore/short-description
```

### Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): brief description

Longer explanation if needed.

Closes #N
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

### PR expectations

- One concern per PR. Do not bundle unrelated fixes.
- PRs that change behavior must include test changes.
- PRs that change architecture must update the relevant doc in `docs/architecture/`.
- PRs that introduce or change a prompt template must update `prompts/`.
- PRs that introduce or change acceptance criteria must update `acceptance/`.

---

## Folder structure and what goes where

| Folder | Purpose |
|---|---|
| `specs/` | Feature specs and design notes scoped to a specific issue or capability |
| `prompts/` | Reusable AI prompts used in this repo's development and pipeline |
| `fixtures/` | Stable test inputs and sample data — small, deterministic, public-domain or synthetic |
| `acceptance/` | Acceptance checklists and criteria definitions for issues and features |
| `tests/` | Automated test files (`test_*.py`). Tests currently live in the root; new tests go in `tests/` |
| `docs/` | Reference documentation; architecture notes in `docs/architecture/` |

When a PR touches behavior in a module, check whether any of the above folders need updating.

---

## Validation — automated vs manual

### Automated (CI-gated, required for merge)

CI runs on every push and PR via `.github/workflows/ci.yml`. It requires only
Python, `pyyaml`, `requests`, `pytest`, and `flake8` — no GPU, no ffmpeg, no
Ollama.

Run locally (same commands as CI):

```bash
# Install CI deps
pip install -r requirements-ci.txt

# Lint
flake8 media_inspect.py compare_core.py config.py models.py orchestrator.py \
  llm_polish.py srt_writer.py audio_utils.py subtitle_utils.py asr.py mt.py \
  tracing.py batch_process.py benchmark.py \
  --select=E9,F --extend-ignore=F401,F841 --exclude venv

# Unit tests (no live services required)
pytest tests/ -v -m "not integration"
```

All new tests go under `tests/`. Fixtures go in `fixtures/`.

### Manual system validation (not CI-gated)

The root-level test scripts (`test_pipeline.py`, `test_orchestrator.py`, etc.)
require live local services (ffmpeg, Faster-Whisper, GPU, Ollama) and are run
manually by the developer. They are not part of the automated CI gate.

```bash
# Full end-to-end validation (requires ffmpeg + GPU + Ollama)
python test_pipeline.py path/to/test.mkv
```

These scripts should remain working but are not the merge gate.

## Testing requirements

- New modules must ship with tests.
- Bug fixes must include a test that would have caught the bug.
- Tests must pass before a PR is opened (not just before merge).
- Test files follow `test_<module>.py` naming.
- Use `pytest`. No framework-specific test runners unless agreed in advance.
- Integration tests that require GPU or a running LLM must be clearly marked (e.g., `@pytest.mark.integration`) and must not block CI on machines without those resources.
- If a change cannot be practically tested (e.g., GPU-only path with no test hardware), document that clearly in the PR and file a follow-up issue.

---

## Acceptance criteria

Every non-trivial PR should link to or embed acceptance criteria. These can be:
- A reference to an issue's acceptance criteria.
- A reference to a file in `acceptance/`.
- An inline checklist in the PR body.

The PR template enforces this. Do not skip it.

---

## Code standards (preserved from prior guide)

### Style

- Follow PEP 8. Max line length: 100 characters (120 for comments/docstrings).
- Use type hints on all public function signatures.
- Class names: `PascalCase`. Functions/methods: `snake_case`. Constants: `UPPER_SNAKE_CASE`.

### Imports

```python
# Standard library
import json
from pathlib import Path

# Third-party
import torch

# Local
from config import Config
from models import Segment
```

### Comments

Only add comments when the why is non-obvious. Do not comment what the code already says.

### Error handling

Be specific with exception types. Include file/model context in error messages. Clean up temp files in `finally` blocks.

### Logging

Use module-level `logger = logging.getLogger(__name__)`. Use `DEBUG` for diagnostics, `INFO` for normal progress, `WARNING` for unexpected-but-recoverable, `ERROR` for failures.

### Security

- Never hardcode credentials or API keys. Use environment variables.
- Pass subprocess commands as lists, not shell strings, to avoid injection.

---

## Questions

Check the existing docs first (`docs/`, `README.md`). If something is unclear about process, open an issue.
