# Fixture: anime

## Description

Short synthetic anime dialogue sample covering common emotional registers:
declaration of intent, disbelief, companionship, perseverance, and aspiration.

## Source

Synthetic — not derived from any copyrighted work.
All Japanese text was composed for testing purposes only.

## Expected translation challenges

- Short exclamatory lines (WER sensitive to single-word differences)
- Informal spoken register (`信じられない` vs `I can't believe it/you`)
- Motivational stock phrases that have multiple plausible English renderings

## Usage

Run the corpus benchmark against this fixture to measure how well each
translation engine handles typical anime dialogue tone and vocabulary.
Reference scores serve as a quality floor: improvements should raise BLEU/chrF
and lower WER relative to the baseline captured in `expected.json`.
