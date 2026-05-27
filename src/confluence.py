"""
Confluence REST API client.
All network calls live here — the rest of the app never calls requests directly.
"""

import json
import os
import sys
from base64 import b64encode

import requests

from src.config import BASE_URL, SPACE_KEY


def _auth_headers() -> dict:
    email = os.environ.get("CONFLUENCE_EMAIL")
    token = os.environ.get("CONFLUENCE_TOKEN")
    if not email or not token:
        sys.exit(
            "ERROR: CONFLUENCE_EMAIL and CONFLUENCE_TOKEN environment variables must be set.\n"
            "  export CONFLUENCE_EMAIL=you@springhealth.com\n"
            "  export CONFLUENCE_TOKEN=<your-atlassian-api-token>"
        )
    encoded = b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# Build once at import time so every call shares the same headers object.
HEADERS = _auth_headers()


def get_page(page_id: str) -> dict:
    """Return full page dict including body.storage and version."""
    resp = requests.get(
        f"{BASE_URL}/content/{page_id}",
        params={"expand": "body.storage,version,title"},
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def update_page(page_id: str, title: str, new_body: str, current_version: int) -> dict:
    """PUT a new version of a page. Increments version by 1."""
    payload = {
        "version": {"number": current_version + 1},
        "title": title,
        "type": "page",
        "body": {
            "storage": {
                "value": new_body,
                "representation": "storage",
            }
        },
    }
    resp = requests.put(
        f"{BASE_URL}/content/{page_id}",
        headers=HEADERS,
        data=json.dumps(payload),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def search_confluence(cql: str, limit: int = 10) -> dict:
    """Run a CQL search, returning results with body.storage expanded."""
    resp = requests.get(
        f"{BASE_URL}/search",
        params={
            "cql": cql,
            "limit": limit,
            "expand": "content.body.storage,content.metadata.labels",
        },
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def build_page_url(page_id: str) -> str:
    return f"https://springhealth.atlassian.net/wiki/spaces/{SPACE_KEY}/pages/{page_id}"
