"""
Central config: page definitions, Confluence coordinates, run constants.
"""

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
CLAUDE_MODEL = "claude-sonnet-4-20250514"

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
