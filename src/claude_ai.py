"""
Claude API integration — gap analysis and status scoring.

Accepts context from multiple sources: Confluence, Slack, Jira, Granola.
"""

import json
import textwrap

import anthropic

from src.config import CLAUDE_MODEL, TODAY

_client = anthropic.Anthropic()


def analyze_page_gaps(
    page_title: str,
    page_body: str,
    sources: dict[str, str],
) -> dict:
    """
    Ask Claude to score the page status, find gaps, and propose fills.

    sources is a dict of source_name -> formatted_text. Supported keys:
        confluence      — CQL search results from other Confluence spaces
        slack           — recent Slack channel messages
        jira            — open Jira issues
        granola         — Granola meeting notes
        direct_input    — explicit instruction text (from --direct or Slack bot DM)

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
    source_block = _format_sources(sources)

    prompt = textwrap.dedent(f"""
        You are auditing a Confluence page for the Spring Health Product Operations
        knowledge center (PO2 space). Your job is to identify gaps and propose fills
        using evidence gathered from multiple sources: Confluence, Slack, Jira, and
        Granola meeting notes.

        PAGE TITLE: {page_title}
        TODAY'S DATE: {TODAY}

        PAGE CONTENT (storage XML):
        {page_body[:6000]}

        {source_block}

        --- SCORING RULES ---
        CURRENT:  content is complete, no [TO FILL] markers, all dates are recent
        PARTIAL:  some [TO FILL] markers remain, or some sections are present but thin
        SKELETON: mostly empty — headers/schema exist but little real content
        STALE:    content is present but dates or data appear outdated (pre-2025)

        --- CONFIDENCE RULES for fill proposals ---
        HIGH:   value is a direct verbatim quote from a source
        MEDIUM: value is strongly implied by a source but not a direct quote
        LOW:    inferred — do NOT propose auto-fill for LOW items

        Use the source name "direct_input" for any information provided via the
        Direct Update Instruction (if present) — treat it as HIGH confidence context
        from the page owner.

        --- OUTPUT ---
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
              "source_name": "page title, Slack channel, Jira key, or meeting title",
              "source_type": "confluence|slack|jira|granola|direct_input"
            }}
          ],
          "panel_message": "human-readable 1-2 sentence message for the info panel",
          "panel_type": "info|note|warning"
        }}
    """).strip()

    response = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
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


def summarize_audit_for_slack(audit_results: list[dict]) -> str:
    """
    Generate a short Slack-friendly summary of an audit run.
    Called by the Slack bot in response to a "status" command.
    """
    if not audit_results:
        return "_No audit data available. Run `python main.py --phase 1` first._"

    lines = ["*Last audit results:*\n"]
    for r in audit_results:
        status = r.get("status", "?")
        title = r.get("fetched_title") or r["page"]["title"]
        fills = r.get("analysis", {}).get("fills", [])
        high = sum(1 for f in fills if f.get("confidence") == "HIGH")
        icon = {"CURRENT": "✅", "PARTIAL": "🟡", "SKELETON": "🔴", "STALE": "🟠", "SKIP": "⚪", "ERROR": "❌"}.get(status, "❓")
        detail = f" ({high} auto-fill ready)" if high else ""
        lines.append(f"{icon} *{title}*: {status}{detail}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_sources(sources: dict[str, str]) -> str:
    """Format the multi-source context block for the Claude prompt."""
    if not sources:
        return "SOURCES: (none available)"

    _LABELS = {
        "confluence": "CONFLUENCE — recent pages from related spaces",
        "slack": "SLACK — recent channel messages",
        "jira": "JIRA — open tickets",
        "granola": "GRANOLA — meeting notes",
        "direct_input": "DIRECT UPDATE INSTRUCTION (treat as HIGH confidence)",
    }

    sections: list[str] = []
    char_budgets = {
        "direct_input": 3000,
        "confluence": 4000,
        "slack": 2000,
        "jira": 2000,
        "granola": 2000,
    }

    for key in ("direct_input", "confluence", "slack", "jira", "granola"):
        text = sources.get(key, "").strip()
        if not text:
            continue
        label = _LABELS.get(key, key.upper())
        budget = char_budgets.get(key, 2000)
        sections.append(f"--- {label} ---\n{text[:budget]}")

    return "\n\n".join(sections) if sections else "SOURCES: (none available)"
