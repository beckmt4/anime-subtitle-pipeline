# attic/

Retired code and scripts that are kept for reference but are no longer part of the active pipeline.

Files here are not collected by pytest (`norecursedirs = attic` in `pytest.ini`) and are not imported by any production code.

| File | Why retired |
|------|-------------|
| `test_pipeline.py` | CLI smoke script predating the pytest suite; replaced by `tests/` |
| `debug_test.py` | Ad-hoc debug harness; superseded by proper test modules |
