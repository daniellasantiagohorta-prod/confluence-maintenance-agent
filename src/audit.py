"""
Phase 1 — Audit: fetch pages, gather multi-source context, score with Claude.

Sources (all optional, fall back gracefully if not configured):
  1. Confluence CQL search   — always enabled
  2. Slack channel search    — requires SLACK_BOT_TOKEN
  3. Jira ticket search      — uses existing CONFLUENCE_TOKEN
  4. Granola meeting notes   — uses local Granola API or GRANOLA_EXPORT_DIR
"""

import requests

from src.claude_ai import analyze_competitive_landscape, analyze_page_gaps
from src.config import (
    COMPETITOR_NAMES,
    GRANOLA_DAYS_BACK,
    JIRA_DAYS_BACK,
    JIRA_PROJECT_KEYS,
    SEARCH_SINCE,
    SLACK_CHANNELS,
    SLACK_DAYS_BACK,
    SOURCE_SPACES,
    SPACE_KEY,
    TODAY,
)
from src.confluence import build_page_url, get_page, search_confluence
from src.granola_connector import search_meeting_notes
from src.jira_connector import search_customer_competitive_insights, search_jira
from src.slack_connector import search_slack_channels
from src.web_search_connector import search_competitive_web

# Page IDs that receive the full competitive discovery treatment
_COMPETITIVE_PAGE_IDS: frozenset[str] = frozenset({"3891724617"})


def run_audit(pages: list[dict]) -> list[dict]:
    """
    Fetch each page, gather context from all sources, ask Claude to score it.
    Returns one result dict per page.
    """
    print("\n" + "=" * 70)
    print("PHASE 1 — AUDIT  (sources: Confluence, Slack, Jira, Granola, Web)")
    print("=" * 70)

    results: list[dict] = []
    for page_cfg in pages:
        pid = page_cfg["id"]
        title = page_cfg["title"]
        rule = page_cfg["rule"]
        level = page_cfg["level"]

        print(f"\n  [{level}] {title} ({rule}) …", end=" ", flush=True)

        try:
            page_data = get_page(pid)
        except requests.HTTPError as exc:
            print(f"FETCH ERROR: {exc}")
            results.append(_error_result(page_cfg, str(exc)))
            continue

        body: str = page_data.get("body", {}).get("storage", {}).get("value", "")
        version: int = page_data.get("version", {}).get("number", 1)
        fetched_title: str = page_data.get("title", title)

        sources = _gather_sources(page_cfg)

        if rule == "SKIP":
            analysis = _skip_analysis()
        elif page_cfg["id"] in _COMPETITIVE_PAGE_IDS:
            analysis = analyze_competitive_landscape(fetched_title, body, sources)
        else:
            analysis = analyze_page_gaps(fetched_title, body, sources)

        print(analysis.get("status", "?"))
        results.append(
            _make_result(page_cfg, page_data, body, version, fetched_title, analysis)
        )

    return results


def run_targeted_audit(page_cfg: dict, extra_context: str = "") -> dict:
    """
    Run a single-page audit, injecting optional extra context (e.g. from a Slack DM).
    Returns a single result dict.
    """
    pid = page_cfg["id"]
    title = page_cfg["title"]
    rule = page_cfg["rule"]

    try:
        page_data = get_page(pid)
    except requests.HTTPError as exc:
        return _error_result(page_cfg, str(exc))

    body: str = page_data.get("body", {}).get("storage", {}).get("value", "")
    version: int = page_data.get("version", {}).get("number", 1)
    fetched_title: str = page_data.get("title", title)

    sources = _gather_sources(page_cfg)

    if extra_context:
        sources["direct_input"] = (
            f"--- Direct update instruction from Slack\n{extra_context}"
        )

    if rule == "SKIP":
        analysis = _skip_analysis()
    elif page_cfg["id"] in _COMPETITIVE_PAGE_IDS:
        analysis = analyze_competitive_landscape(fetched_title, body, sources)
    else:
        analysis = analyze_page_gaps(fetched_title, body, sources)

    return _make_result(page_cfg, page_data, body, version, fetched_title, analysis)


def print_audit_summary(audit_results: list[dict]) -> None:
    print("\n" + "=" * 70)
    print("AUDIT SUMMARY")
    print("=" * 70)

    for result in audit_results:
        page_cfg = result["page"]
        status = result.get("status", "ERROR")
        analysis = result.get("analysis", {})
        fills = analysis.get("fills", [])
        high = sum(1 for f in fills if f.get("confidence") == "HIGH")
        medium = sum(1 for f in fills if f.get("confidence") == "MEDIUM")
        gaps = analysis.get("gaps", [])

        url = build_page_url(page_cfg["id"])
        print(
            f"  {status.ljust(10)}  [{page_cfg['level']}] {page_cfg['title']}"
            f"  ({page_cfg['rule']})"
        )
        if result.get("error"):
            print(f"             ERROR: {result['error']}")
        else:
            if gaps:
                gap_preview = ", ".join(gaps[:3])
                if len(gaps) > 3:
                    gap_preview += f" … +{len(gaps)-3} more"
                print(f"             gaps: {gap_preview}")
            if high or medium:
                print(f"             fills proposed: {high} HIGH, {medium} MEDIUM")
            rationale = analysis.get("rationale", "")
            if rationale:
                print(f"             {rationale}")
        print(f"             {url}")

    print()


# ---------------------------------------------------------------------------
# Source gathering
# ---------------------------------------------------------------------------

def _gather_sources(page_cfg: dict) -> dict[str, str]:
    """
    Collect context from all configured sources for one page.
    Returns a dict of source_name -> formatted_text.

    Competitive Landscape pages additionally pull from:
      5. External web search (Brave / SerpAPI / domain scrape)
      6. Jira customer competitive signals (feature-parity, win-loss labels)
    """
    keywords = page_cfg["keywords"]
    is_competitive = page_cfg["id"] in _COMPETITIVE_PAGE_IDS

    sources: dict[str, str] = {}

    # 1. Confluence
    sources["confluence"] = _run_confluence_search(keywords)

    # 2. Slack (broader keyword set for competitive pages to catch competitor mentions)
    if SLACK_CHANNELS:
        slack_keywords = keywords + COMPETITOR_NAMES[:6] if is_competitive else keywords
        sources["slack"] = search_slack_channels(slack_keywords, SLACK_CHANNELS, SLACK_DAYS_BACK)

    # 3. Jira (standard ticket search)
    sources["jira"] = search_jira(keywords, JIRA_PROJECT_KEYS, JIRA_DAYS_BACK)

    # 4. Granola meeting notes
    sources["granola"] = search_meeting_notes(keywords, GRANOLA_DAYS_BACK)

    # 5 & 6. Competitive-only sources
    if is_competitive:
        print(" [web+customer discovery]", end="", flush=True)
        sources["web"] = search_competitive_web()
        sources["customer_competitive"] = search_customer_competitive_insights(
            COMPETITOR_NAMES, JIRA_PROJECT_KEYS, JIRA_DAYS_BACK * 3
        )

    return sources


def _run_confluence_search(keywords: list[str]) -> str:
    spaces_cql = '", "'.join(SOURCE_SPACES)
    keyword_clause = " OR ".join(f'text ~ "{kw}"' for kw in keywords[:3])
    cql = (
        f'space in ("{spaces_cql}") '
        f'AND lastmodified >= "{SEARCH_SINCE}" '
        f'AND ({keyword_clause})'
    )
    try:
        data = search_confluence(cql, limit=8)
        return _format_confluence_results(data)
    except requests.HTTPError:
        return "(Confluence search unavailable)"


def _format_confluence_results(search_data: dict) -> str:
    results = search_data.get("results", [])
    if not results:
        return "(no recent results found)"
    lines = []
    for item in results:
        content = item.get("content", {})
        cid = content.get("id", "")
        ctitle = content.get("title", "(untitled)")
        excerpt = item.get("excerpt", "")
        url = f"https://springhealth.atlassian.net/wiki/spaces/{SPACE_KEY}/pages/{cid}"
        lines.append(f"--- [{ctitle}]({url})\n{excerpt[:500]}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Result constructors
# ---------------------------------------------------------------------------

def _skip_analysis() -> dict:
    return {
        "status": "SKIP",
        "rationale": "Leadership-owned page — info panel update only.",
        "gaps": [],
        "fills": [],
        "panel_message": f"Content maintained by leadership. Last agent audit: {TODAY}.",
        "panel_type": "info",
    }


def _make_result(
    page_cfg: dict,
    page_data: dict,
    body: str,
    version: int,
    fetched_title: str,
    analysis: dict,
) -> dict:
    return {
        "page": page_cfg,
        "error": None,
        "status": analysis.get("status", "PARTIAL"),
        "analysis": analysis,
        "page_data": page_data,
        "current_body": body,
        "current_version": version,
        "fetched_title": fetched_title,
    }


def _error_result(page_cfg: dict, error: str) -> dict:
    return {
        "page": page_cfg,
        "error": error,
        "status": "ERROR",
        "analysis": {},
        "page_data": None,
        "current_body": "",
        "current_version": 1,
        "fetched_title": page_cfg["title"],
    }
