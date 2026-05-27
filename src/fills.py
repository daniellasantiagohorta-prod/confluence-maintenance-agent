"""
Phase 2 — Info panel updates (all pages)
Phase 3 — Gap fills (REVIEW pages, HIGH confidence only)
"""

import requests

from src.config import TODAY
from src.confluence import build_page_url, update_page
from src.panels import build_info_panel, inject_panel_into_body


# ---------------------------------------------------------------------------
# Phase 2 — Info panels
# ---------------------------------------------------------------------------

def run_panel_updates(audit_results: list[dict], dry_run: bool) -> list[dict]:
    """
    Inject or replace the status info panel at the top of every page.
    SKIP pages get a CURRENT panel; REVIEW pages get their audit status.
    Body content is never modified here.
    """
    print("\n" + "=" * 70)
    print("PHASE 2 — INFO PANEL UPDATES")
    print("=" * 70)

    changes: list[dict] = []
    for result in audit_results:
        if result.get("error"):
            print(f"  SKIP (fetch error): {result['fetched_title']}")
            continue

        page_cfg = result["page"]
        analysis = result["analysis"]
        title = result["fetched_title"]
        body = result["current_body"]
        version = result["current_version"]
        status = result["status"]

        panel_status = "CURRENT" if status == "SKIP" else status
        panel_message = analysis.get("panel_message", f"Audited {TODAY}.")
        if TODAY not in panel_message:
            panel_message += f" (Audited: {TODAY}.)"

        panel_xml = build_info_panel(panel_status, panel_message)
        new_body = inject_panel_into_body(body, panel_xml)

        label = "DRY-RUN" if dry_run else "UPDATING"
        print(f"  [{label}] {title} — {panel_status}")

        change = {
            "page": title,
            "page_id": page_cfg["id"],
            "phase": 2,
            "field": "info panel",
            "old_value": "(previous panel or none)",
            "new_value": f"{panel_status} panel",
            "source": "confluence-maintenance-agent",
            "confidence": "N/A",
        }

        if not dry_run:
            try:
                update_page(page_cfg["id"], title, new_body, version)
                result["current_version"] = version + 1
                result["current_body"] = new_body
                print(f"    ✓ Updated")
            except requests.HTTPError as exc:
                print(f"    ✗ Update failed: {exc}")
                change["new_value"] = f"FAILED: {exc}"

        changes.append(change)

    return changes


# ---------------------------------------------------------------------------
# Phase 3 — Gap fills
# ---------------------------------------------------------------------------

def run_gap_fills(audit_results: list[dict], dry_run: bool) -> list[dict]:
    """
    For REVIEW pages:
    - HIGH confidence → auto-fill (unless dry_run)
    - MEDIUM confidence → surface in report, never write
    - LOW confidence → leave as [TO FILL]
    """
    print("\n" + "=" * 70)
    print(
        "PHASE 3 — GAP FILLS"
        + (" (DRY-RUN — showing proposals only)" if dry_run else " (HIGH confidence only)")
    )
    print("=" * 70)

    changes: list[dict] = []
    for result in audit_results:
        if result.get("error") or result["page"]["rule"] == "SKIP":
            continue

        page_cfg = result["page"]
        analysis = result.get("analysis", {})
        fills = analysis.get("fills", [])

        if not fills:
            print(f"\n  {result['fetched_title']}: no fills proposed")
            continue

        high = [f for f in fills if f.get("confidence") == "HIGH"]
        medium = [f for f in fills if f.get("confidence") == "MEDIUM"]
        low = [f for f in fills if f.get("confidence") == "LOW"]

        print(
            f"\n  {result['fetched_title']}: "
            f"{len(high)} HIGH / {len(medium)} MEDIUM / {len(low)} LOW"
        )

        # Always surface MEDIUM fills for human review (never write them)
        for f in medium:
            print(
                f"    [MEDIUM — review] {f['field']} "
                f"← \"{str(f.get('value',''))[:60]}\" "
                f"(Source: {f.get('source_name','?')})"
            )
            changes.append(_fill_change(result, f, applied=False))

        if not high:
            continue

        body = result["current_body"]
        version = result["current_version"]
        modified = False

        for f in high:
            field = f.get("field", "")
            value = str(f.get("value", ""))
            source_name = f.get("source_name", "")
            source_url = f.get("source_url", "")

            # Only substitute when the marker is actually in the page body
            if "[TO FILL]" not in body and field not in body:
                print(f"    [SKIP] '{field}' marker not found in body")
                continue

            sourced_value = _annotate_value(value, source_name, source_url)

            if field in body:
                idx = body.index(field)
                to_fill_idx = body.find("[TO FILL]", idx)
                if to_fill_idx != -1:
                    body = body[:to_fill_idx] + sourced_value + body[to_fill_idx + 9:]
                    modified = True
            elif "[TO FILL]" in body:
                body = body.replace("[TO FILL]", sourced_value, 1)
                modified = True

            label = "DRY-RUN" if dry_run else "FILLING"
            print(
                f"    [{label} HIGH] {field} "
                f"← \"{value[:60]}\" "
                f"(Source: {source_name})"
            )
            changes.append(_fill_change(result, f, applied=not dry_run))

        if modified and not dry_run:
            try:
                update_page(
                    page_cfg["id"],
                    result["fetched_title"],
                    body,
                    version,
                )
                result["current_version"] += 1
                result["current_body"] = body
                print(f"    ✓ Page updated")
            except requests.HTTPError as exc:
                print(f"    ✗ Update failed: {exc}")

    return changes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _annotate_value(value: str, source_name: str, source_url: str | None) -> str:
    """Wrap a fill value with a sourced-from footnote in storage XML."""
    if source_url:
        return (
            f'{value} <sup><em>(Source: <a href="{source_url}">{source_name}</a>'
            f" — verified {TODAY})</em></sup>"
        )
    return f"{value} <sup><em>(Source: {source_name} — verified {TODAY})</em></sup>"


def _fill_change(result: dict, fill: dict, applied: bool) -> dict:
    status = "APPLIED" if applied else f"SURFACED ({fill.get('confidence','?')})"
    return {
        "page": result["fetched_title"],
        "page_id": result["page"]["id"],
        "phase": 3,
        "field": fill.get("field", ""),
        "old_value": "[TO FILL]",
        "new_value": fill.get("value", "") if applied else f"[NOT WRITTEN] {fill.get('value','')}",
        "source": fill.get("source_name", ""),
        "source_url": fill.get("source_url"),
        "confidence": fill.get("confidence", "?"),
        "status": status,
    }
