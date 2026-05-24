-- Migration 001: Add source_language column to subtitle_candidates.
--
-- For translated candidates (source='mt' or 'mt_llm') this records the
-- ISO 639-1 language that was translated FROM (e.g. 'ja' when language='en').
-- For ASR and embedded candidates the value is NULL (source and output language
-- are the same).
ALTER TABLE subtitle_candidates ADD COLUMN source_language TEXT;
