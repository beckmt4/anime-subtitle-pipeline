"""core.benchmark.html_report — HTML benchmark report renderer.

Generates a self-contained HTML report from benchmark_results.json output,
with:
- Run summary header (video name, reference candidate, timestamp)
- Candidate scorecard table ranked by quality metrics
- Per-comparison diff viewer with highlighted text differences
- Embedded CSS (no external dependencies)

Usage::

    from core.benchmark.html_report import render_html_report

    html = render_html_report(results)          # returns HTML string
    render_html_report(results, output_path)    # writes to file and returns string
"""

from __future__ import annotations

import html as _html
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSS — embedded in the report so it is fully self-contained
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px;
       color: #222; background: #f5f5f5; padding: 24px; }
h1 { font-size: 1.6em; margin-bottom: 4px; }
h2 { font-size: 1.15em; margin: 24px 0 8px; color: #444; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
.meta { color: #666; font-size: 0.88em; margin-bottom: 20px; }
table { border-collapse: collapse; width: 100%; background: #fff;
        box-shadow: 0 1px 3px rgba(0,0,0,.12); margin-bottom: 20px; }
th { background: #2c3e50; color: #fff; padding: 8px 12px; text-align: left; font-weight: 600; }
td { padding: 7px 12px; border-bottom: 1px solid #eee; vertical-align: top; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #f0f4f8; }
.ref-row td { background: #eaf6ea; font-weight: 600; }
.rank-1 td:first-child { color: #27ae60; font-weight: 700; }
.metric-good { color: #27ae60; font-weight: 600; }
.metric-bad  { color: #c0392b; }
.pill { display: inline-block; padding: 2px 8px; border-radius: 10px;
        font-size: 0.82em; font-weight: 600; }
.pill-embedded { background: #d5e8d4; color: #1a6b1a; }
.pill-asr      { background: #dae8fc; color: #1a3a6b; }
.pill-mt       { background: #fff2cc; color: #6b5b00; }
.pill-other    { background: #e8e8e8; color: #555; }
.diff-block { background: #fff; border: 1px solid #ddd; border-radius: 6px;
              padding: 12px 16px; margin-bottom: 12px; }
.diff-block .timing { font-size: 0.82em; color: #888; margin-bottom: 6px; }
.diff-ref  { background: #ffeef0; border-left: 3px solid #c0392b;
             padding: 4px 8px; margin: 2px 0; border-radius: 2px; }
.diff-cand { background: #e6ffed; border-left: 3px solid #27ae60;
             padding: 4px 8px; margin: 2px 0; border-radius: 2px; }
.diff-label { font-size: 0.78em; font-weight: 700; color: #888;
              text-transform: uppercase; margin-right: 6px; }
.comparison-header { display: flex; justify-content: space-between;
                     align-items: center; margin-bottom: 8px; }
.comparison-header .ids { font-weight: 600; }
.comparison-header .metrics-inline { font-size: 0.88em; color: #555; }
.warning-banner { background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px;
                  padding: 10px 16px; margin-bottom: 16px; color: #856404; font-weight: 600; }
.no-diffs { color: #888; font-style: italic; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 4px;
         font-size: 0.82em; background: #2c3e50; color: #fff; margin-left: 8px; }
.warning-banner { background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px;
                  padding: 10px 16px; margin-bottom: 16px; color: #856404; font-size: 0.95em; }
"""

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _e(text: str) -> str:
    """HTML-escape a string."""
    return _html.escape(str(text))


def _source_pill(source: str) -> str:
    s = source.lower()
    # Check composite sources before single-label sources to avoid mis-classification.
    # e.g. "ja_audio_asr_mt" contains both "asr" and "mt" → should be mt/pipeline pill.
    if "asr" in s and ("mt" in s or "llm" in s):
        cls = "pill-mt"
    elif "embedded" in s and "mt" not in s and "llm" not in s:
        cls = "pill-embedded"
    elif "asr" in s:
        cls = "pill-asr"
    elif "mt" in s or "llm" in s:
        cls = "pill-mt"
    else:
        cls = "pill-other"
    return f'<span class="pill {cls}">{_e(source)}</span>'


def _fmt_wer(v: float) -> str:
    pct = v * 100
    cls = "metric-good" if pct <= 20 else ("metric-bad" if pct >= 60 else "")
    return f'<span class="{cls}">{pct:.1f}%</span>'


def _fmt_bleu(v: float) -> str:
    cls = "metric-good" if v >= 60 else ("metric-bad" if v < 25 else "")
    return f'<span class="{cls}">{v:.1f}</span>'


def _fmt_chrf(v: float) -> str:
    cls = "metric-good" if v >= 70 else ("metric-bad" if v < 35 else "")
    return f'<span class="{cls}">{v:.1f}</span>'


# ---------------------------------------------------------------------------
# Scorecard builder
# ---------------------------------------------------------------------------

def build_scorecards(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build per-candidate scorecards from benchmark results.

    Each scorecard contains the candidate metadata merged with its best metrics
    from any comparison where it was the hypothesis candidate.  Scorecards are
    ranked by a composite score: ``0.5*(1-WER) + 0.25*(BLEU/100) + 0.25*(chrF/100)``.

    Args:
        results: Dict as returned by :func:`benchmark.run_benchmark`.

    Returns:
        List of scorecard dicts, sorted best → worst.  Each dict has keys:
        ``id``, ``source``, ``segment_count``, ``language``, ``is_reference``,
        ``wer``, ``bleu``, ``chrf``, ``composite_score``, ``origin_stream``,
        and any extra metadata from the candidate entry.
    """
    reference_id = results.get("reference_id", "")
    comparisons_by_cand: Dict[str, List[Dict[str, Any]]] = {}
    for comp in results.get("comparisons", []):
        cid = comp.get("cand_id", "")
        comparisons_by_cand.setdefault(cid, []).append(comp)

    scorecards = []
    for cand_meta in results.get("candidates", []):
        cid = cand_meta.get("id", "")
        is_ref = cid == reference_id

        # Pick the comparison against the reference, or the best available.
        comps = comparisons_by_cand.get(cid, [])
        ref_comps = [c for c in comps if c.get("ref_id") == reference_id]
        chosen_comp = ref_comps[0] if ref_comps else (comps[0] if comps else None)

        if chosen_comp:
            metrics = chosen_comp.get("metrics", {})
            wer = metrics.get("wer", None)
            bleu = metrics.get("bleu", None)
            chrf = metrics.get("chrf", None)
        else:
            wer = bleu = chrf = None

        if wer is not None and bleu is not None and chrf is not None:
            composite = 0.5 * (1.0 - wer) + 0.25 * (bleu / 100.0) + 0.25 * (chrf / 100.0)
        else:
            composite = 1.0 if is_ref else None

        scorecard = {
            "id": cid,
            "source": cand_meta.get("source", "unknown"),
            "segment_count": cand_meta.get("segment_count", 0),
            "language": cand_meta.get("language", "en"),
            "origin_stream": cand_meta.get("origin_stream", ""),
            "is_reference": is_ref,
            "wer": wer,
            "bleu": bleu,
            "chrf": chrf,
            "composite_score": composite,
        }
        # Carry over optional metadata keys
        for extra_key in ("translation_engine", "translation_model", "translation_mode",
                          "translation_fallback"):
            if extra_key in cand_meta:
                scorecard[extra_key] = cand_meta[extra_key]
        scorecards.append(scorecard)

    # Sort: reference first, then by composite score descending (best → worst), nulls last
    def _scorecard_sort_key(sc):
        if sc["is_reference"]:
            return (2, 0.0)   # highest group → always first with reverse=True
        c = sc["composite_score"]
        return (1, c) if c is not None else (0, 0.0)  # nulls in group 0 → last

    scorecards.sort(key=_scorecard_sort_key, reverse=True)
    # Assign rank (1-based, reference excluded from ranking)
    rank = 1
    for sc in scorecards:
        if sc["is_reference"]:
            sc["rank"] = "REF"
        else:
            sc["rank"] = rank
            rank += 1

    return scorecards


# ---------------------------------------------------------------------------
# HTML section builders
# ---------------------------------------------------------------------------

def _render_scorecard_table(scorecards: List[Dict[str, Any]]) -> str:
    rows = []
    for sc in scorecards:
        is_ref = sc["is_reference"]
        row_cls = 'ref-row' if is_ref else (f'rank-{sc["rank"]}' if sc["rank"] == 1 else "")

        rank_cell = "REF" if is_ref else str(sc["rank"])
        wer_cell = _fmt_wer(sc["wer"]) if sc["wer"] is not None else "—"
        bleu_cell = _fmt_bleu(sc["bleu"]) if sc["bleu"] is not None else "—"
        chrf_cell = _fmt_chrf(sc["chrf"]) if sc["chrf"] is not None else "—"
        composite_cell = (f'{sc["composite_score"]:.3f}' if sc["composite_score"] is not None
                          else "—")

        rows.append(
            f'<tr class="{row_cls}">'
            f'<td>{rank_cell}</td>'
            f'<td>{_e(sc["id"])}</td>'
            f'<td>{_source_pill(sc["source"])}</td>'
            f'<td>{sc["segment_count"]}</td>'
            f'<td>{wer_cell}</td>'
            f'<td>{bleu_cell}</td>'
            f'<td>{chrf_cell}</td>'
            f'<td>{composite_cell}</td>'
            f'</tr>'
        )

    return (
        '<table>'
        '<thead><tr>'
        '<th>Rank</th><th>Candidate ID</th><th>Source</th><th>Segments</th>'
        '<th>WER ↓</th><th>BLEU ↑</th><th>chrF ↑</th><th>Composite ↑</th>'
        '</tr></thead>'
        '<tbody>' + "".join(rows) + '</tbody>'
        '</table>'
    )


def _render_comparisons(results: Dict[str, Any], max_diffs: int = 20) -> str:
    comparisons = results.get("comparisons", [])
    if not comparisons:
        return '<p class="no-diffs">No comparisons recorded.</p>'

    blocks = []
    for comp in comparisons:
        ref_id = _e(comp.get("ref_id", "?"))
        cand_id = _e(comp.get("cand_id", "?"))
        metrics = comp.get("metrics", {})
        wer = metrics.get("wer", 0.0)
        bleu = metrics.get("bleu", 0.0)
        chrf = metrics.get("chrf", 0.0)
        num_segs = comp.get("num_segments", 0)
        num_diffs = comp.get("num_diffs", 0)
        diffs = comp.get("diffs", [])[:max_diffs]

        metrics_inline = (
            f'WER {wer*100:.1f}% &nbsp;|&nbsp; '
            f'BLEU {bleu:.1f} &nbsp;|&nbsp; '
            f'chrF {chrf:.1f} &nbsp;|&nbsp; '
            f'{num_diffs} diffs / {num_segs} segments'
        )

        diff_html = ""
        if diffs:
            diff_items = []
            for d in diffs:
                start = d.get("start", 0.0)
                end = d.get("end", 0.0)
                ref_text = _e(d.get("ref", ""))
                cand_text = _e(d.get("cand", ""))
                diff_items.append(
                    f'<div class="diff-block">'
                    f'<div class="timing">{start:.2f}s – {end:.2f}s</div>'
                    f'<div class="diff-ref"><span class="diff-label">ref</span>{ref_text}</div>'
                    f'<div class="diff-cand"><span class="diff-label">cand</span>{cand_text}</div>'
                    f'</div>'
                )
            diff_html = "".join(diff_items)
        else:
            diff_html = '<p class="no-diffs">No significant text differences found.</p>'

        blocks.append(
            f'<div style="margin-bottom:28px">'
            f'<div class="comparison-header">'
            f'<div class="ids">{ref_id} <span style="color:#888">vs</span> {cand_id}</div>'
            f'<div class="metrics-inline">{metrics_inline}</div>'
            f'</div>'
            + diff_html +
            '</div>'
        )

    return "".join(blocks)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_html_report(
    results: Dict[str, Any],
    output_path: Optional[str] = None,
    *,
    generated_at: Optional[str] = None,
) -> str:
    """Render a self-contained HTML benchmark report.

    Args:
        results:       Dict as returned by :func:`benchmark.run_benchmark`.
        output_path:   If provided, write the HTML to this path (parent dirs are
                       created automatically) and return the HTML string.
        generated_at:  ISO-8601 timestamp override (defaults to now, UTC).

    Returns:
        Full HTML document as a string.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    video = _e(results.get("video", "unknown"))
    reference_id = _e(results.get("reference_id", "—"))
    run_id = _e(results.get("run_id", "—"))
    num_candidates = len(results.get("candidates", []))
    num_comparisons = len(results.get("comparisons", []))
    status = results.get("status", "ok")
    warning = results.get("warning", "")

    scorecards = build_scorecards(results)

    warning_html = ""
    if num_comparisons == 0:
        warning_msg = _e(results.get(
            "warning",
            "No comparisons produced — only one candidate was available or all "
            "non-reference candidates were skipped.",
        ))
        warning_html = f'<div class="warning-banner">⚠ {warning_msg}</div>'

    scorecard_table = _render_scorecard_table(scorecards)

    if status == "single_candidate_only":
        comparisons_html = (
            '<div class="warning-banner">'
            '⚠ No benchmark comparison possible — only one candidate was generated.'
            '</div>'
        )
    else:
        comparisons_html = _render_comparisons(results)

    warning_banner = ""
    if status == "single_candidate_only":
        warning_banner = (
            f'<div class="warning-banner">'
            f'⚠ <strong>Single candidate only:</strong> {_e(warning)}'
            f'</div>\n'
        )

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Benchmark Report — {video}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Benchmark Report <span class="badge">{video}</span></h1>
{warning_banner}<p class="meta">
  Generated: {_e(generated_at)} &nbsp;|&nbsp;
  Run ID: <code>{run_id}</code> &nbsp;|&nbsp;
  Reference: <strong>{reference_id}</strong> &nbsp;|&nbsp;
  Candidates: {num_candidates} &nbsp;|&nbsp;
  Comparisons: {num_comparisons}
</p>
{warning_html}
<h2>Candidate Scorecards</h2>
{scorecard_table}

<h2>Comparison Diffs</h2>
{comparisons_html}
</body>
</html>
"""
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_doc, encoding="utf-8")
        logger.info("HTML benchmark report written: %s", out)

    return html_doc


__all__ = ["render_html_report", "build_scorecards"]
