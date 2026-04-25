"""Subtitle corrector using a local Ollama instance.

Accepts a parsed SRT as a list of cue dicts and returns a corrected SRT string.
Calls Ollama /api/chat to fix grammar, punctuation, and natural English flow
without changing meaning, names, or structure.

Usage as a library:
    from subtitle_corrector import correct_srt

    with open("episode.srt", encoding="utf-8") as f:
        cues = parse_srt(f.read())
    corrected = correct_srt(cues, model="mistral")

Usage from CLI:
    python subtitle_corrector.py input.srt -o corrected.srt
    python subtitle_corrector.py input.srt --model llama3
    python subtitle_corrector.py input.srt --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, NamedTuple

import requests

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = "mistral"
BATCH_SIZE = 20

_SYSTEM_PROMPT = (
    "You are a subtitle editor. Your ONLY job is to fix grammar, punctuation, "
    "and natural English flow in subtitle text translated from Japanese.\n\n"
    "STRICT RULES:\n"
    "- Do NOT change any nouns, names, or proper nouns\n"
    "- Do NOT add words, context, or meaning not present in the source\n"
    "- Do NOT change character names, place names, or item names — even if they seem wrong\n"
    "- Do NOT paraphrase or rewrite — only fix grammar and flow\n"
    "- Preserve the original meaning exactly\n"
    "- Preserve all line breaks (\\N) and formatting tags\n"
    "- If a line is already correct, return it unchanged\n"
    "- Return ONLY the corrected subtitle text, nothing else"
)

_CAPITALIZED_RE = re.compile(r"\b[A-Z][a-zA-Z]+\b")
_QUOTED_RE = re.compile(r'["\']([^"\']+)["\']')


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

@dataclass
class DriftEvent:
    index: int
    raw: str
    llm: str
    reason: str   # "noun_change" | "length_ratio"
    detail: str   # noun string | ratio string
    timestamp: str  # ISO 8601


class CorrectionStats(NamedTuple):
    cues_in: int
    cues_out: int
    corrected: int
    drift_reverted: int


def _extract_nouns(text: str) -> set:
    """Extract capitalized words (2+ chars) and quoted terms from text."""
    nouns = set(_CAPITALIZED_RE.findall(text))
    nouns.update(_QUOTED_RE.findall(text))
    return nouns


def check_drift(raw: str, llm: str) -> Tuple[bool, str, str]:
    """Check whether an LLM correction has drifted from the raw cue.

    Returns (is_drift, reason, detail).
    Noun check runs before length check — nouns are non-negotiable.
    """
    if raw == llm:
        return (False, "", "")

    for noun in _extract_nouns(raw):
        if noun not in llm:
            return (True, "noun_change", noun)

    raw_words = raw.split()
    if raw_words:
        ratio = len(llm.split()) / len(raw_words)
        if ratio > 1.4 or ratio < 0.6:
            return (True, "length_ratio", f"{ratio:.2f}")

    return (False, "", "")


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _format_timestamp(seconds: float) -> str:
    """Format a float seconds value as an SRT timestamp HH:MM:SS,mmm."""
    if seconds < 0:
        raise ValueError(f"Timestamp cannot be negative: {seconds}")
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _to_timestamp_str(value) -> str:
    """Return an SRT timestamp string from either a float (seconds) or a pre-formatted string."""
    if isinstance(value, (int, float)):
        return _format_timestamp(float(value))
    return str(value)


# ---------------------------------------------------------------------------
# Prompt construction and response parsing
# ---------------------------------------------------------------------------

def _build_user_message(batch: List[Dict]) -> str:
    """Format a batch of cues as a numbered list for the LLM."""
    return "\n".join(f"{i}. {cue['text']}" for i, cue in enumerate(batch, start=1))


def _parse_numbered_response(response: str, batch: List[Dict]) -> Dict[int, str]:
    """Parse a numbered LLM response into a {batch_position: corrected_text} dict.

    Matches lines starting with `N.` or `N)`. Cue positions not found in the
    response fall back to the original text so the output is always complete.
    """
    result: Dict[int, str] = {}
    line_re = re.compile(r"^\s*(\d+)[.)]\s*(.*)", re.MULTILINE)

    for match in line_re.finditer(response):
        pos = int(match.group(1))
        text = match.group(2).strip()
        if text:
            result[pos] = text

    for i, cue in enumerate(batch, start=1):
        if i not in result:
            logger.warning(
                "No corrected text in response for cue %d (index %s); keeping original",
                i,
                cue.get("index"),
            )
            result[i] = cue["text"]

    return result


# ---------------------------------------------------------------------------
# Ollama API call
# ---------------------------------------------------------------------------

def _call_ollama(
    system_prompt: str,
    user_message: str,
    model: str,
    timeout: int = 120,
) -> str:
    """POST to Ollama /api/chat and return the assistant reply text.

    Raises RuntimeError on connection failure, timeout, or empty reply.
    Subprocess commands are intentionally absent — this module uses HTTP only.
    """
    if not OLLAMA_BASE_URL.startswith(("http://localhost", "http://127.0.0.1")):
        logger.warning("Non-localhost Ollama endpoint: %s", OLLAMA_BASE_URL)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Could not connect to Ollama at {OLLAMA_BASE_URL}. "
            "Is `ollama serve` running?"
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Ollama request timed out after {timeout}s. "
            "Try a smaller batch or increase --timeout."
        )
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"Ollama API error: {exc}") from exc

    data = response.json()
    reply = data.get("message", {}).get("content", "").strip()
    if not reply:
        raise RuntimeError(f"Ollama returned an empty reply for model '{model}'. Raw: {data}")
    return reply


# ---------------------------------------------------------------------------
# SRT rendering
# ---------------------------------------------------------------------------

def _render_srt(cues: List[Dict]) -> str:
    """Render cue dicts back to a complete SRT string."""
    blocks: List[str] = []
    for cue in cues:
        start = _to_timestamp_str(cue["start"])
        end = _to_timestamp_str(cue["end"])
        # Normalise \N (ASS hard line-break) to a real newline for SRT output.
        text = cue["text"].replace("\\N", "\n").replace("\\n", "\n")
        blocks.append(f"{cue['index']}\n{start} --> {end}\n{text}")
    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _run_correction(
    cues: List[Dict],
    effective_model: str,
    batch_size: int,
    timeout: int,
    dry_run: bool,
    verbose: bool,
    drift_log: Optional[str],
    label: str,
) -> Tuple[str, CorrectionStats]:
    """Inner implementation shared by correct_srt() and correct_srt_ex()."""
    corrected = [dict(cue) for cue in cues]
    batches = [cues[i:i + batch_size] for i in range(0, len(cues), batch_size)]

    logger.info(
        "Correcting %d cues in %d batch(es) with model '%s'",
        len(cues),
        len(batches),
        effective_model,
    )

    total_corrected = 0
    total_drift_reverted = 0
    drift_events: List[DriftEvent] = []

    for batch_idx, batch in enumerate(batches):
        user_message = _build_user_message(batch)

        if dry_run:
            if batch_idx == 0:
                print("=== DRY RUN — batch 1 Ollama prompt ===\n")
                print(f"[SYSTEM]\n{_SYSTEM_PROMPT}\n")
                print(f"[USER]\n{user_message}\n")
                print("=== (no API call made) ===")
            continue

        logger.info(
            "Batch %d/%d — %d cues",
            batch_idx + 1,
            len(batches),
            len(batch),
        )

        reply = _call_ollama(_SYSTEM_PROMPT, user_message, effective_model, timeout)
        corrections = _parse_numbered_response(reply, batch)

        index_to_correction = {
            batch[i - 1]["index"]: corrections[i] for i in range(1, len(batch) + 1)
        }

        for cue in corrected:
            if cue["index"] not in index_to_correction:
                continue
            raw_text = cue["text"]
            llm_text = index_to_correction[cue["index"]]

            is_drift, reason, detail = check_drift(raw_text, llm_text)
            if is_drift:
                event = DriftEvent(
                    index=cue["index"],
                    raw=raw_text,
                    llm=llm_text,
                    reason=reason,
                    detail=detail,
                    timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
                drift_events.append(event)
                total_drift_reverted += 1

                if verbose:
                    print(f"DRIFT REVERTED #{cue['index']}:")
                    print(f"  RAW: {raw_text}")
                    print(f"  LLM: {llm_text}")
                    print(f"  REASON: {reason} ({detail})")
            elif llm_text != raw_text:
                cue["text"] = llm_text
                total_corrected += 1

    if not dry_run:
        print(
            f"[corrector] {label}: {len(cues)} cues processed, "
            f"{total_corrected} corrected, {total_drift_reverted} drift-reverted"
        )

        if drift_log and drift_events:
            try:
                with open(drift_log, "a", encoding="utf-8") as fh:
                    for event in drift_events:
                        fh.write(json.dumps(asdict(event)) + "\n")
            except OSError as exc:
                logger.warning("Could not write drift log to %s: %s", drift_log, exc)

    srt = _render_srt(corrected)
    stats = CorrectionStats(
        cues_in=len(cues),
        cues_out=len(corrected),
        corrected=total_corrected,
        drift_reverted=total_drift_reverted,
    )
    return srt, stats


def correct_srt(
    cues: List[Dict],
    model: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
    timeout: int = 120,
    dry_run: bool = False,
    verbose: bool = False,
    drift_log: Optional[str] = None,
    label: str = "",
) -> str:
    """Correct subtitle grammar and flow using a local Ollama model.

    Args:
        cues: List of dicts, each with keys: index, start, end, text.
              start/end may be float seconds or pre-formatted SRT timestamp strings.
        model: Ollama model name. Falls back to the MODEL env var, then "mistral".
        batch_size: Number of cues per API call (default 20).
        timeout: Per-request HTTP timeout in seconds.
        dry_run: If True, print the system prompt + first-batch user message and
                 return the original SRT unchanged without calling the API.
        verbose: Print a DRIFT REVERTED block for each reverted cue.
        drift_log: Path to a file for JSON-lines drift event output (append mode).
        label: Label used in the summary line (typically the filename).

    Returns:
        Corrected SRT as a complete string with original timing preserved exactly.

    Raises:
        ValueError: If cues is empty.
        RuntimeError: If Ollama is unreachable or returns an unusable response.
    """
    if not cues:
        raise ValueError("correct_srt: cues list is empty")
    effective_model = model or os.environ.get("MODEL", DEFAULT_MODEL)
    srt, _ = _run_correction(cues, effective_model, batch_size, timeout, dry_run, verbose,
                             drift_log, label)
    return srt


def correct_srt_ex(
    cues: List[Dict],
    model: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
    timeout: int = 120,
    dry_run: bool = False,
    verbose: bool = False,
    drift_log: Optional[str] = None,
    label: str = "",
) -> Tuple[str, CorrectionStats]:
    """Like correct_srt() but also returns a CorrectionStats named tuple.

    Returns:
        (corrected_srt, CorrectionStats(cues_in, cues_out, corrected, drift_reverted))

    All other args and exceptions are identical to correct_srt().
    """
    if not cues:
        raise ValueError("correct_srt_ex: cues list is empty")
    effective_model = model or os.environ.get("MODEL", DEFAULT_MODEL)
    return _run_correction(cues, effective_model, batch_size, timeout, dry_run, verbose,
                           drift_log, label)


# ---------------------------------------------------------------------------
# SRT file parser (for the CLI; also usable as a library helper)
# ---------------------------------------------------------------------------

def parse_srt(content: str) -> List[Dict]:
    """Parse SRT file content into a list of cue dicts.

    Each dict has: index (int), start (str), end (str), text (str).
    """
    blocks = re.split(r"\n{2,}", content.strip())
    timestamp_re = re.compile(
        r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})"
    )
    cues: List[Dict] = []

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0].strip())
        except ValueError:
            logger.debug("Skipping non-index block starting with: %r", lines[0])
            continue
        match = timestamp_re.match(lines[1].strip())
        if not match:
            logger.debug("Skipping block %d — could not parse timestamp: %r", index, lines[1])
            continue
        text = "\n".join(lines[2:])
        cues.append({
            "index": index,
            "start": match.group(1),
            "end": match.group(2),
            "text": text,
        })

    return cues


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Correct SRT subtitle grammar and flow using a local Ollama model. "
            "Timing is never changed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Model resolution order: --model flag > MODEL env var > 'mistral'\n\n"
            "Examples:\n"
            "  python subtitle_corrector.py episode.srt -o episode.fixed.srt\n"
            "  python subtitle_corrector.py episode.srt --model llama3 --dry-run\n"
            "  MODEL=qwen2.5:7b python subtitle_corrector.py episode.srt"
        ),
    )
    parser.add_argument("input", help="Input SRT file")
    parser.add_argument("-o", "--output", help="Output SRT file (default: stdout)")
    parser.add_argument(
        "--model",
        default=None,
        help="Ollama model name (overrides MODEL env var; default: mistral)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print the system prompt and first-batch user message without "
            "calling the Ollama API. Useful for inspecting what the model will receive."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each drift-reverted cue with raw, LLM output, and reason.",
    )
    parser.add_argument(
        "--drift-log",
        metavar="PATH",
        default=None,
        help="Append drift events as JSON lines to this file.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        with open(args.input, encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)
    except OSError as exc:
        logger.error("Could not read %s: %s", args.input, exc)
        sys.exit(1)

    cues = parse_srt(content)
    if not cues:
        logger.error("No cues parsed from %s — check the file format", args.input)
        sys.exit(1)

    logger.info("Parsed %d cues from %s", len(cues), args.input)

    try:
        result = correct_srt(
            cues,
            model=args.model,
            dry_run=args.dry_run,
            verbose=args.verbose,
            drift_log=args.drift_log,
            label=os.path.basename(args.input),
        )
    except RuntimeError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    if args.dry_run:
        return

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(result)
            logger.info("Written to %s", args.output)
        except OSError as exc:
            logger.error("Could not write %s: %s", args.output, exc)
            sys.exit(1)
    else:
        sys.stdout.write(result)


if __name__ == "__main__":
    main()


__all__ = ["correct_srt", "correct_srt_ex", "parse_srt", "check_drift", "_extract_nouns",
           "CorrectionStats", "DriftEvent"]
