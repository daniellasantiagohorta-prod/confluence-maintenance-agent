"""
Claude API integration — gap analysis and status scoring.
"""

import json
import textwrap

import anthropic

from src.config import CLAUDE_MODEL, TODAY

_client = anthropic.Anthropic()


def analyze_page_gaps(page_title: str, page_body: str, search_results_text: str) -> dict:
    """
    Ask Claude to score the page status, find gaps, and propose fills.

    Returns a dict with keys:
        status          CURRENT | PARTIAL | SKELETON | STALE
        rationale       one-sentence reason
        gaps            list of [TO FILL] markers / missing fields
        fills           list of {field, value, confidence, source_url, source_name}
        panel_message   human-readable sentence for the info panel
        panel_type      info | note | warning

    Never raises — returns a safe PARTIAL fallback if Claude's response can't
    be parsed as JSON.
    """
    prompt = textwrap.dedent(f"""
        You are auditing a Confluence page for the Spring Health Product Operations
        knowledge center (PO2 space).

        PAGE TITLE: {page_title}
        TODAY'S DATE: {TODAY}

        PAGE CONTENT (storage XML):
        {page_body[:6000]}

        SEARCH RESULTS FROM OTHER CONFLUENCE SPACES (recent pages, since 2026-01-01):
        {search_results_text[:4000]}

        Scoring rules:
        - CURRENT: content is complete, no [TO FILL] markers, dates are recent
        - PARTIAL: some [TO FILL] markers remain, or some data is present but incomplete
        - SKELETON: mostly empty — schema/headers exist but little real content
        - STALE: content is present but dates or data appear outdated (pre-2025)

        Gap-fill confidence rules:
        - HIGH: value is a direct verbatim quote from a search result page
        - MEDIUM: value is strongly implied by a search result but not a direct quote
        - LOW: inferred, not directly sourced — do NOT propose auto-fill

        Respond with valid JSON only (no markdown fences), exactly this shape:
        {{
          "status": "CURRENT|PARTIAL|SKELETON|STALE",
          "rationale": "one-sentence reason for the score",
          "gaps": ["list of [TO FILL] markers or missing fields found"],
          "fills": [
            {{
              "field": "exact field name or [TO FILL] marker text",
              "value": "proposed replacement value",
              "confidence": "HIGH|MEDIUM|LOW",
              "source_url": "full URL if available, else null",
              "source_name": "page or doc title"
            }}
          ],
          "panel_message": "human-readable 1-2 sentence message for the info panel",
          "panel_type": "info|note|warning"
        }}
    """).strip()

    response = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "status": "PARTIAL",
            "rationale": f"Claude response could not be parsed as JSON: {exc}",
            "gaps": ["(parse error — manual review required)"],
            "fills": [],
            "panel_message": (
                f"Audit attempted {TODAY}; automated analysis failed. "
                "Manual review required."
            ),
            "panel_type": "note",
        }
