"""
External web search connector — competitive intelligence.

Searches the public web for competitor news, product updates, and market signals.

Backends (tried in order):
  1. Brave Search API  (BRAVE_SEARCH_API_KEY) — https://api.search.brave.com
     Free tier: 2,000 requests/month.  Sign up at the URL above.
  2. SerpAPI           (SERP_API_KEY)          — https://serpapi.com
  3. URL-scrape fallback — fetches COMPETITOR_DOMAINS pages directly (no key needed,
     but limited to publicly accessible static pages).

Set one of the API keys in your .env for best results.
"""

import os
import re

import requests

from src.config import COMPETITOR_DOMAINS, COMPETITOR_NAMES

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_SERP_ENDPOINT = "https://serpapi.com/search"

# Search queries issued per competitor (first two are sent; third only if time permits)
_QUERY_TEMPLATES = [
    "{name} new product features OR announcement 2025 2026",
    "{name} employee mental health platform customer review",
    "{name} funding OR partnership OR integration 2025 2026",
]


def search_competitive_web(max_results_per_query: int = 5) -> str:
    """
    Search the public web for recent competitor intelligence.
    Returns formatted text for use as Claude context.
    Falls back gracefully at each level if credentials are missing.
    """
    brave_key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    serp_key = os.environ.get("SERP_API_KEY", "").strip()

    if brave_key:
        result = _search_brave(brave_key, max_results_per_query)
        if result:
            return result

    if serp_key:
        result = _search_serp(serp_key, max_results_per_query)
        if result:
            return result

    return _scrape_competitor_domains()


# ---------------------------------------------------------------------------
# Brave Search
# ---------------------------------------------------------------------------

def _search_brave(api_key: str, max_results: int) -> str:
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    sections: list[str] = []

    for name in COMPETITOR_NAMES[:7]:
        for template in _QUERY_TEMPLATES[:2]:
            query = template.format(name=name)
            try:
                resp = requests.get(
                    _BRAVE_ENDPOINT,
                    headers=headers,
                    params={"q": query, "count": max_results, "freshness": "py"},
                    timeout=15,
                )
                resp.raise_for_status()
            except requests.RequestException:
                continue

            results = resp.json().get("web", {}).get("results", [])
            if not results:
                continue

            lines = [f"--- Web ({name}): {query}"]
            for r in results[:max_results]:
                age = r.get("age") or r.get("page_age", "")
                title = r.get("title", "")
                desc = r.get("description", "")
                url = r.get("url", "")
                lines.append(f"[{age}] {title}")
                if desc:
                    lines.append(f"  {desc[:300]}")
                lines.append(f"  {url}")
            sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else ""


# ---------------------------------------------------------------------------
# SerpAPI
# ---------------------------------------------------------------------------

def _search_serp(api_key: str, max_results: int) -> str:
    sections: list[str] = []

    for name in COMPETITOR_NAMES[:7]:
        query = f"{name} mental health platform product update OR new features 2025 2026"
        try:
            resp = requests.get(
                _SERP_ENDPOINT,
                params={
                    "q": query,
                    "api_key": api_key,
                    "num": max_results,
                    "tbs": "qdr:y",  # past year
                },
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException:
            continue

        organic = resp.json().get("organic_results", [])
        if not organic:
            continue

        lines = [f"--- Web ({name})"]
        for r in organic[:max_results]:
            date = r.get("date", "")
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            link = r.get("link", "")
            lines.append(f"[{date}] {title}")
            if snippet:
                lines.append(f"  {snippet[:300]}")
            lines.append(f"  {link}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections) if sections else ""


# ---------------------------------------------------------------------------
# URL-scrape fallback
# ---------------------------------------------------------------------------

def _scrape_competitor_domains() -> str:
    """
    Fetch each competitor's domain page and strip HTML to plain text.
    Used when no search API key is configured.
    """
    sections: list[str] = []

    for name, url in list(COMPETITOR_DOMAINS.items())[:7]:
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; confluence-maintenance-bot/1.0)"},
                timeout=12,
                allow_redirects=True,
            )
            if resp.status_code != 200:
                continue
            # Strip HTML tags; collapse whitespace; keep first 1200 chars
            text = re.sub(r"<script[^>]*>.*?</script>", " ", resp.text, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()[:1200]
            sections.append(f"--- Web (scraped): {name} ({url})\n{text}")
        except requests.RequestException:
            continue

    if not sections:
        return (
            "(No external web search API configured and domain scrape unavailable. "
            "Set BRAVE_SEARCH_API_KEY or SERP_API_KEY in .env for live web intelligence.)"
        )
    return "\n\n".join(sections)
