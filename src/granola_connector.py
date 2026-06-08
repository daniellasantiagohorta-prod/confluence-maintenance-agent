"""
Granola connector — surface relevant meeting notes from the Granola Mac app.

Granola stores its data in an encrypted local database, but exposes a REST API
through its desktop app on localhost. This connector uses that local API.

Two modes (tried in order):
  1. Granola local API  — works when the Granola desktop app is running
  2. Export folder scan — works if you export notes to GRANOLA_EXPORT_DIR
                          (set in your .env, defaults to ~/Documents/GranolaExports)

Granola local API is unauthenticated on localhost (port 1618 by default).
If the app is not running, mode 1 silently falls back to mode 2.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

_GRANOLA_LOCAL_PORT = int(os.environ.get("GRANOLA_LOCAL_PORT", "1618"))
_GRANOLA_LOCAL_BASE = f"http://localhost:{_GRANOLA_LOCAL_PORT}"


def search_meeting_notes(
    keywords: list[str],
    days_back: int = 30,
) -> str:
    """
    Search Granola meeting notes for mentions of keywords.
    Tries the local API first, then falls back to an export folder.
    Returns formatted text for use as Claude context.
    """
    result = _search_via_local_api(keywords, days_back)
    if result is not None:
        return result

    result = _search_export_folder(keywords, days_back)
    if result is not None:
        return result

    return "(Granola not reachable — start the Granola app or set GRANOLA_EXPORT_DIR)"


# ---------------------------------------------------------------------------
# Mode 1: Granola local API
# ---------------------------------------------------------------------------

def _search_via_local_api(keywords: list[str], days_back: int) -> Optional[str]:
    """
    Query Granola's local API (app must be running).
    Returns None if the API is not available.
    """
    try:
        resp = requests.get(
            f"{_GRANOLA_LOCAL_BASE}/api/documents",
            timeout=3,
        )
        resp.raise_for_status()
        documents = resp.json()
    except (requests.RequestException, ValueError):
        return None  # app not running or incompatible version

    if not isinstance(documents, list):
        return None

    cutoff = datetime.now() - timedelta(days=days_back)
    results: list[str] = []

    for doc in documents:
        created_str = doc.get("created_at") or doc.get("createdAt") or ""
        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if created.replace(tzinfo=None) < cutoff:
                continue
        except (ValueError, AttributeError):
            pass

        title = doc.get("title") or doc.get("name") or "(untitled)"
        content = _extract_doc_content(doc)
        content_lower = content.lower()

        if not any(kw.lower() in content_lower for kw in keywords):
            continue

        snippets = _extract_snippets(content, keywords)
        if not snippets:
            continue

        date_str = created_str[:10] if created_str else "unknown date"
        results.append(f"--- Meeting: {title} ({date_str})")
        results.extend(snippets[:3])

    return "\n\n".join(results) if results else "(no relevant meeting notes found via Granola API)"


def _extract_doc_content(doc: dict) -> str:
    """Pull plain text from various Granola document shapes."""
    # Try common field names
    for field in ("content", "body", "notes", "transcript", "text"):
        val = doc.get(field)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, dict):
            # Might be a structured document (ProseMirror / Tiptap)
            return _flatten_prosemirror(val)

    # Nested notes object
    notes = doc.get("notes") or {}
    if isinstance(notes, dict):
        return _flatten_prosemirror(notes)

    return json.dumps(doc)[:1000]


def _flatten_prosemirror(node: dict) -> str:
    """Flatten a ProseMirror/Tiptap JSON document to plain text."""
    texts: list[str] = []

    def traverse(n):
        if isinstance(n, dict):
            if n.get("type") == "text":
                texts.append(n.get("text", ""))
            for child in n.get("content", []):
                traverse(child)
        elif isinstance(n, list):
            for item in n:
                traverse(item)

    traverse(node)
    return " ".join(texts)


# ---------------------------------------------------------------------------
# Mode 2: Export folder scan
# ---------------------------------------------------------------------------

_DEFAULT_EXPORT_DIR = Path.home() / "Documents" / "GranolaExports"


def _search_export_folder(keywords: list[str], days_back: int) -> Optional[str]:
    """
    Scan a folder of exported Granola notes (markdown or JSON files).
    Returns None if the folder doesn't exist.
    """
    export_dir_str = os.environ.get("GRANOLA_EXPORT_DIR", str(_DEFAULT_EXPORT_DIR))
    export_dir = Path(export_dir_str)

    if not export_dir.exists():
        return None

    cutoff = datetime.now() - timedelta(days=days_back)
    results: list[str] = []

    for path in sorted(export_dir.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file() or path.suffix not in (".md", ".txt", ".json"):
            continue

        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if mtime < cutoff:
            continue

        try:
            raw = path.read_text(errors="ignore")
        except OSError:
            continue

        if path.suffix == ".json":
            try:
                data = json.loads(raw)
                text = _extract_doc_content(data) if isinstance(data, dict) else raw
            except (json.JSONDecodeError, ValueError):
                text = raw
        else:
            text = raw

        if not any(kw.lower() in text.lower() for kw in keywords):
            continue

        snippets = _extract_snippets(text, keywords)
        if not snippets:
            continue

        date_str = mtime.strftime("%Y-%m-%d")
        title = _infer_title(text, path.stem)
        results.append(f"--- Meeting: {title} ({date_str})")
        results.extend(snippets[:3])

    return "\n\n".join(results) if results else "(no relevant meeting notes found in export folder)"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _extract_snippets(text: str, keywords: list[str]) -> list[str]:
    snippets: list[str] = []
    lines = text.split("\n")
    lower_kws = [kw.lower() for kw in keywords]
    for i, line in enumerate(lines):
        if not any(kw in line.lower() for kw in lower_kws):
            continue
        start = max(0, i - 1)
        end = min(len(lines), i + 2)
        chunk = " | ".join(l.strip() for l in lines[start:end] if l.strip())
        if chunk:
            snippets.append(f"  > {chunk[:350]}")
    return snippets


def _infer_title(text: str, fallback: str) -> str:
    for line in text.split("\n")[:5]:
        stripped = line.strip().lstrip("#").strip()
        if stripped and len(stripped) < 120:
            return stripped
    return fallback
