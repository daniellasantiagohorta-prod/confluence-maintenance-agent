"""
Jira connector — search tickets and epics for context on tracked topics.

Uses the same Atlassian credentials as the Confluence connector:
  CONFLUENCE_EMAIL   — your @springhealth.com email
  CONFLUENCE_TOKEN   — Atlassian API token

No extra credentials required.
"""

import os
from base64 import b64encode
from typing import Optional

import requests


_JIRA_BASE = "https://springhealth.atlassian.net/rest/api/3"
_BROWSE_BASE = "https://springhealth.atlassian.net/browse"


def search_jira(
    keywords: list[str],
    project_keys: list[str],
    days_back: int = 30,
    max_results: int = 8,
) -> str:
    """
    Search Jira for open issues updated in the last N days that mention keywords.
    Returns formatted text for use as Claude context.

    Falls back gracefully if credentials are missing.
    """
    headers = _auth_headers()
    if not headers:
        return "(Jira credentials not configured)"

    jql = _build_jql(keywords, project_keys, days_back)

    try:
        resp = requests.get(
            f"{_JIRA_BASE}/search",
            headers=headers,
            params={
                "jql": jql,
                "maxResults": max_results,
                "fields": "summary,status,assignee,description,updated,issuetype,priority,labels",
            },
            timeout=20,
        )
        resp.raise_for_status()
    except requests.HTTPError as exc:
        return f"(Jira search failed: {exc})"
    except requests.RequestException:
        return "(Jira search unavailable)"

    issues = resp.json().get("issues", [])
    if not issues:
        return "(no relevant Jira issues found)"

    lines: list[str] = []
    for issue in issues:
        key = issue.get("key", "")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        status = fields.get("status", {}).get("name", "")
        issue_type = fields.get("issuetype", {}).get("name", "")
        updated = (fields.get("updated") or "")[:10]
        url = f"{_BROWSE_BASE}/{key}"
        labels = fields.get("labels") or []
        label_str = f"  labels: {', '.join(labels)}" if labels else ""

        lines.append(f"--- [{key}] [{issue_type}] {summary}")
        lines.append(f"  status: {status} | updated: {updated}{label_str}")

        desc_text = _extract_description(fields.get("description"))
        if desc_text:
            lines.append(f"  {desc_text[:350]}")

        lines.append(f"  {url}")

    return "\n".join(lines)


def search_customer_competitive_insights(
    competitor_names: list[str],
    project_keys: list[str],
    days_back: int = 90,
    max_results: int = 15,
) -> str:
    """
    Search Jira for customer-reported competitive gaps, feature requests,
    and win/loss signals.

    Looks for issues with:
    - Labels: customer-request, competitor, feature-parity, win-loss, churn
    - Summaries/descriptions mentioning competitor names
    Returns formatted text for Claude context.
    """
    headers = _auth_headers()
    if not headers:
        return "(Jira credentials not configured)"

    competitor_text_clause = " OR ".join(
        f'text ~ "{name}"' for name in competitor_names[:8]
    )
    label_clause = (
        'labels in ("customer-request", "competitor", "feature-parity", '
        '"win-loss", "churn", "feature-request", "enterprise-feedback")'
    )

    parts: list[str] = []
    if project_keys:
        projects = ", ".join(f'"{k}"' for k in project_keys)
        parts.append(f"project in ({projects})")
    parts.append(f"updated >= -{days_back}d")
    parts.append(f"({label_clause} OR ({competitor_text_clause}))")

    jql = " AND ".join(parts) + " ORDER BY updated DESC"

    try:
        resp = requests.get(
            f"{_JIRA_BASE}/search",
            headers=headers,
            params={
                "jql": jql,
                "maxResults": max_results,
                "fields": "summary,status,assignee,description,updated,issuetype,priority,labels,comment",
            },
            timeout=20,
        )
        resp.raise_for_status()
    except requests.HTTPError as exc:
        return f"(Jira customer insights search failed: {exc})"
    except requests.RequestException:
        return "(Jira search unavailable)"

    issues = resp.json().get("issues", [])
    if not issues:
        return "(no customer competitive insights found in Jira)"

    lines: list[str] = []
    for issue in issues:
        key = issue.get("key", "")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")
        status = fields.get("status", {}).get("name", "")
        issue_type = fields.get("issuetype", {}).get("name", "")
        updated = (fields.get("updated") or "")[:10]
        url = f"{_BROWSE_BASE}/{key}"
        labels = fields.get("labels") or []
        label_str = f"  labels: {', '.join(labels)}" if labels else ""

        lines.append(f"--- [{key}] [{issue_type}] {summary}")
        lines.append(f"  status: {status} | updated: {updated}{label_str}")

        desc_text = _extract_description(fields.get("description"))
        if desc_text:
            lines.append(f"  {desc_text[:400]}")
        lines.append(f"  {url}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _auth_headers() -> dict:
    email = os.environ.get("CONFLUENCE_EMAIL")
    token = os.environ.get("CONFLUENCE_TOKEN")
    if not email or not token:
        return {}
    encoded = b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _build_jql(keywords: list[str], project_keys: list[str], days_back: int) -> str:
    keyword_clause = " OR ".join(f'text ~ "{kw}"' for kw in keywords[:4])

    parts: list[str] = []

    if project_keys:
        projects = ", ".join(f'"{k}"' for k in project_keys)
        parts.append(f"project in ({projects})")

    parts.append(f"updated >= -{days_back}d")
    parts.append(f"({keyword_clause})")

    return " AND ".join(parts) + " ORDER BY updated DESC"


def _extract_description(desc: Optional[dict]) -> str:
    """Extract plain text from Atlassian Document Format (ADF) v3."""
    if not desc or not isinstance(desc, dict):
        return ""

    texts: list[str] = []

    def traverse(node: dict) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "text":
            texts.append(node.get("text", ""))
        for child in node.get("content", []):
            traverse(child)

    traverse(desc)
    return " ".join(texts).strip()
