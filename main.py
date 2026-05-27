#!/usr/bin/env python3
"""
Confluence Knowledge Maintenance Agent — Spring Health PO2
Entry point and CLI argument handling.

Usage:
    python main.py --dry-run          # full audit, zero Confluence writes
    python main.py                    # live run (all phases)
    python main.py --phase 1          # audit only, print report, stop
    python main.py --phase 2          # info panels only
    python main.py --phase 3          # gap fills only
    python main.py --pages 3890610497 3896967190   # restrict to specific page IDs
"""

import argparse
import sys

import requests

from src.audit import print_audit_summary, run_audit
from src.config import PAGES, TODAY
from src.confluence import get_page
from src.fills import run_gap_fills, run_panel_updates
from src.report import generate_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Confluence Knowledge Maintenance Agent — Spring Health PO2"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full audit and print proposals but make zero Confluence writes.",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3],
        help="Run only a specific phase (1=audit, 2=panels, 3=fills). "
             "Omit to run all phases in sequence.",
    )
    parser.add_argument(
        "--pages",
        nargs="+",
        metavar="PAGE_ID",
        help="Restrict run to specific Confluence page IDs (space-separated).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dry_run: bool = args.dry_run

    # Resolve page list
    target_pages = PAGES
    if args.pages:
        id_set = set(args.pages)
        target_pages = [p for p in PAGES if p["id"] in id_set]
        if not target_pages:
            sys.exit(f"No pages found matching IDs: {args.pages}")

    print(f"\nConfluence Maintenance Agent — Spring Health PO2")
    print(f"Mode  : {'DRY-RUN (read-only)' if dry_run else 'LIVE'}")
    print(f"Date  : {TODAY}")
    print(f"Pages : {len(target_pages)} targeted")

    phase2_changes: list[dict] = []
    phase3_changes: list[dict] = []

    # ------------------------------------------------------------------
    # Phase 1 — Audit
    # ------------------------------------------------------------------
    if args.phase is None or args.phase == 1:
        audit_results = run_audit(target_pages)
        print_audit_summary(audit_results)
    else:
        # Skipping Phase 1 — do a lightweight fetch so phases 2/3 have page data
        print("\n(Phase 1 skipped — fetching pages for panel/fill operations)")
        audit_results = _lightweight_fetch(target_pages)

    if args.phase == 1:
        generate_report(audit_results, [], [], dry_run)
        print(
            "\nPhase 1 complete. Review the report, then re-run without "
            "--phase 1 to apply changes."
        )
        return

    # ------------------------------------------------------------------
    # Phase 2 — Info panels
    # ------------------------------------------------------------------
    if args.phase is None or args.phase == 2:
        phase2_changes = run_panel_updates(audit_results, dry_run)

    # ------------------------------------------------------------------
    # Phase 3 — Gap fills
    # ------------------------------------------------------------------
    if args.phase is None or args.phase == 3:
        phase3_changes = run_gap_fills(audit_results, dry_run)

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    generate_report(audit_results, phase2_changes, phase3_changes, dry_run)

    print("\n" + "=" * 70)
    if dry_run:
        print("DRY-RUN COMPLETE — no Confluence pages were modified.")
        print("Review the audit report, then run without --dry-run to apply changes.")
    else:
        print("DONE — see the audit report for a full change log.")
    print("=" * 70 + "\n")


def _lightweight_fetch(pages: list[dict]) -> list[dict]:
    """Fetch pages without Claude analysis for use when Phase 1 is skipped."""
    results: list[dict] = []
    for page_cfg in pages:
        try:
            page_data = get_page(page_cfg["id"])
            body = page_data.get("body", {}).get("storage", {}).get("value", "")
            version = page_data.get("version", {}).get("number", 1)
            results.append({
                "page": page_cfg,
                "error": None,
                "status": "PARTIAL",
                "analysis": {
                    "status": "PARTIAL",
                    "rationale": "Phase 1 skipped — no Claude analysis.",
                    "gaps": [],
                    "fills": [],
                    "panel_message": f"Maintenance agent run {TODAY}.",
                    "panel_type": "info",
                },
                "page_data": page_data,
                "current_body": body,
                "current_version": version,
                "fetched_title": page_data.get("title", page_cfg["title"]),
            })
        except requests.HTTPError as exc:
            results.append({
                "page": page_cfg,
                "error": str(exc),
                "status": "ERROR",
                "analysis": {},
                "page_data": None,
                "current_body": "",
                "current_version": 1,
                "fetched_title": page_cfg["title"],
            })
    return results


if __name__ == "__main__":
    main()
