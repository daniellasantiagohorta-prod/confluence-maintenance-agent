"""
Phase 1 — Audit: fetch pages, search for source material, score with Claude.
"""

import requests

from src.claude_ai import analyze_page_gaps
from src.config import SEARCH_SINCE, SOURCE_SPACES, SPACE_KEY, TODAY
from src.confluence import build_page_url, get_page, search_confluence


def run_audit(pages: list[dict]) -> list[dict]:
    """
    Fetch each page, run CQL searches, ask Claude to score it.
    Returns one result dict per page (see _make_result for shape).
    """
    print("\n" + "=" * 70)
    print("PHASE 1 — AUDIT")
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

        search_text = _run_search(page_cfg["keywords"])

        if rule == "SKIP":
            analysis = _skip_analysis()
        else:
            analysis = analyze_page_gaps(fetched_title, body, search_text)

        print(analysis.get("status", "?"))
        results.append(
            _make_result(page_cfg, page_data, body, version, fetched_title, analysis)
        )

    return results


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
# Internal helpers
# ---------------------------------------------------------------------------

def _run_search(keywords: list[str]) -> str:
    spaces_cql = '", "'.join(SOURCE_SPACES)
    keyword_clause = " OR ".join(f'text ~ "{kw}"' for kw in keywords[:3])
    cql = (
        f'space in ("{spaces_cql}") '
        f'AND lastmodified >= "{SEARCH_SINCE}" '
        f'AND ({keyword_clause})'
    )
    try:
        data = search_confluence(cql, limit=8)
        return _format_search_results(data)
    except requests.HTTPError:
        return "(search unavailable)"


def _format_search_results(search_data: dict) -> str:
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
