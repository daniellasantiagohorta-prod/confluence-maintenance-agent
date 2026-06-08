"""
Central config: page definitions, Confluence coordinates, run constants.
"""

import os
from datetime import date

TODAY: str = date.today().isoformat()

# Confluence coordinates
BASE_URL = "https://springhealth.atlassian.net/wiki/rest/api"
SPACE_KEY = "PO2"
SPACE_ID = "3891167389"

# Spaces searched for source material (CQL)
SOURCE_SPACES = ["MX", "PE", "CV", "PCS", "ENG"]
SEARCH_SINCE = "2026-01-01"

# Claude model
CLAUDE_MODEL = "claude-sonnet-4-5"

# ---------------------------------------------------------------------------
# Slack — channel search source
# Set SLACK_CHANNELS in .env as a comma-separated list, e.g.:
#   SLACK_CHANNELS=product-ops,po2-updates,member-growth-team,eng-platform
# ---------------------------------------------------------------------------
_slack_channels_env = os.environ.get(
    "SLACK_CHANNELS",
    "product-ops,po2-updates,member-growth-team,eng-platform,design-research",
)
SLACK_CHANNELS: list[str] = [
    ch.strip().lstrip("#") for ch in _slack_channels_env.split(",") if ch.strip()
]
SLACK_DAYS_BACK: int = int(os.environ.get("SLACK_DAYS_BACK", "21"))

# ---------------------------------------------------------------------------
# Jira — ticket search source
# Set JIRA_PROJECT_KEYS in .env as a comma-separated list, e.g.:
#   JIRA_PROJECT_KEYS=PO,PE,MX,CV
# Leave blank to search across all projects.
# ---------------------------------------------------------------------------
_jira_projects_env = os.environ.get("JIRA_PROJECT_KEYS", "PO,PE,MX,CV,ENG")
JIRA_PROJECT_KEYS: list[str] = [
    k.strip() for k in _jira_projects_env.split(",") if k.strip()
]
JIRA_DAYS_BACK: int = int(os.environ.get("JIRA_DAYS_BACK", "30"))

# ---------------------------------------------------------------------------
# Granola — meeting notes source
# GRANOLA_EXPORT_DIR: folder of exported .md/.json meeting notes (optional).
#   Defaults to ~/Documents/GranolaExports — create it and drop exports there,
#   or leave unset to use the Granola local API (app must be running).
# ---------------------------------------------------------------------------
GRANOLA_DAYS_BACK: int = int(os.environ.get("GRANOLA_DAYS_BACK", "30"))

# ---------------------------------------------------------------------------
# Page registry
# Each entry: id, title, level (L1/L2), rule (SKIP|REVIEW), keywords
# ---------------------------------------------------------------------------

PAGES: list[dict] = [
    # L1 — Product Foundations (parent: 3891396962)
    {
        "id": "3891659024",
        "title": "Product Vision & Strategy",
        "level": "L1",
        "rule": "SKIP",
        "keywords": ["product vision", "strategy", "roadmap"],
    },
    {
        "id": "3890610497",
        "title": "North Star Metrics",
        "level": "L1",
        "rule": "REVIEW",
        "keywords": ["north star", "KPI", "metric", "OKR"],
    },
    {
        "id": "3890479561",
        "title": "User Personas & Segments",
        "level": "L1",
        "rule": "REVIEW",
        "keywords": ["persona", "segment", "member", "user research"],
    },
    {
        "id": "3891233109",
        "title": "Product Principles",
        "level": "L1",
        "rule": "SKIP",
        "keywords": ["principles", "values", "design principles"],
    },
    {
        "id": "3891724617",
        "title": "Competitive Landscape",
        "level": "L1",
        "rule": "REVIEW",
        "keywords": ["competitor", "competitive", "market", "landscape"],
    },
    {
        "id": "3891560725",
        "title": "Product Glossary",
        "level": "L1",
        "rule": "REVIEW",
        "keywords": ["glossary", "definition", "term", "terminology"],
    },
    # L2 — Domain Context (parent: 3897360418)
    {
        "id": "3898114058",
        "title": "Product Area Overviews",
        "level": "L2",
        "rule": "REVIEW",
        "keywords": ["product area", "pod", "team", "squad", "ownership"],
    },
    {
        "id": "3896967190",
        "title": "Feature Registry",
        "level": "L2",
        "rule": "REVIEW",
        "keywords": ["feature", "registry", "feature flag", "launch"],
    },
    {
        "id": "3897655306",
        "title": "Technical Constraints",
        "level": "L2",
        "rule": "REVIEW",
        "keywords": ["technical constraint", "limitation", "dependency", "architecture"],
    },
    {
        "id": "3897655332",
        "title": "Data Model Overview",
        "level": "L2",
        "rule": "REVIEW",
        "keywords": ["data model", "schema", "entity", "database"],
    },
    {
        "id": "3896115318",
        "title": "Integration Map",
        "level": "L2",
        "rule": "REVIEW",
        "keywords": ["integration", "API", "third-party", "connector", "webhook"],
    },
]
