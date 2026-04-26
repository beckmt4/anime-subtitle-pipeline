# Artifact Registry Migrations

Place persistent SQLite schema changes here as numbered SQL files:

```text
001_initial_change.sql
002_add_some_column.sql
```

`core.artifacts.schema.init_db()` applies unapplied `*.sql` files in filename
order and records each filename plus SHA-256 checksum in `schema_migrations`.
Do not edit a migration after it has shipped; add a new numbered file instead.

The `artifacts.artifact_type` column currently stores:

- `srt` — generated subtitle files.
- `qc_json` — quality-control report files.
- `mkv` — muxed/burned-in video deliverables derived from an accepted SRT candidate.
