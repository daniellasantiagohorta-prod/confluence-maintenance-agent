#!/usr/bin/env python3
"""
Confluence Knowledge Maintenance Agent — Spring Health PO2

Keeps the PO2 knowledge base accurate and up to date by pulling context from
Confluence, Slack, Jira, and Granola meeting notes.

Modes:
  python main.py --dry-run          full audit across all sources, zero writes
  python main.py                    live run (audit + panels + fills)
  python main.py --phase 1          audit only (generates report)
  python main.py --phase 2          info panels only
  python main.py --phase 3          gap fills only
  python main.py --pages 3890610497 3896967190  restrict to specific page IDs

  python main.py --direct "update Feature Registry: dark mode launched 2026-05-30"
                            inject explicit context, run targeted update, exit

  python main.py --listen           start the Slack bot and block (for use as a service)
                                    combine with --dry-run to preview without writing
"""

import argparse
import sys
import time

import requests

from src.audit import print_audit_summary, run_audit, run_targeted_audit
from src.claude_ai import summarize_audit_for_slack
from src.config import PAGES, TODAY
from src.confluence import get_page
from src.fills import run_gap_fills, run_panel_updates
from src.report import generate_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Confluence Knowledge Maintenance Agent — Spring Health PO2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        help="Run only a specific phase (1=audit, 2=panels, 3=fills).",
    )
    parser.add_argument(
        "--pages",
        nargs="+",
        metavar="PAGE_ID",
        help="Restrict run to specific Confluence page IDs (space-separated).",
    )
    parser.add_argument(
        "--direct",
        metavar="INSTRUCTION",
        help=(
            'Inject an explicit update instruction and trigger a targeted run. '
            'Format: "update <page name>: <what changed>" '
            'or just describe a change and the agent will find the right page(s).'
        ),
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help=(
            "Start the Slack bot and block. "
            "Requires SLACK_BOT_TOKEN and SLACK_APP_TOKEN in your environment."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dry_run: bool = args.dry_run

    # ------------------------------------------------------------------
    # --direct: targeted single-instruction update
    # ------------------------------------------------------------------
    if args.direct:
        _run_direct(args.direct, dry_run)
        return

    # ------------------------------------------------------------------
    # --listen: Slack bot mode (blocks until Ctrl+C)
    # ------------------------------------------------------------------
    if args.listen:
        _run_listen_mode(dry_run)
        return

    # ------------------------------------------------------------------
    # Normal batch run
    # ------------------------------------------------------------------
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
    print(f"Sources: Confluence, Slack, Jira, Granola")

    phase2_changes: list[dict] = []
    phase3_changes: list[dict] = []

    # Phase 1 — Audit
    if args.phase is None or args.phase == 1:
        audit_results = run_audit(target_pages)
        print_audit_summary(audit_results)
    else:
        print("\n(Phase 1 skipped — fetching pages for panel/fill operations)")
        audit_results = _lightweight_fetch(target_pages)

    if args.phase == 1:
        generate_report(audit_results, [], [], dry_run)
        print(
            "\nPhase 1 complete. Review the report, then re-run without "
            "--phase 1 to apply changes."
        )
        return

    # Phase 2 — Info panels
    if args.phase is None or args.phase == 2:
        phase2_changes = run_panel_updates(audit_results, dry_run)

    # Phase 3 — Gap fills
    if args.phase is None or args.phase == 3:
        phase3_changes = run_gap_fills(audit_results, dry_run)

    # Report
    generate_report(audit_results, phase2_changes, phase3_changes, dry_run)

    print("\n" + "=" * 70)
    if dry_run:
        print("DRY-RUN COMPLETE — no Confluence pages were modified.")
        print("Review the audit report, then run without --dry-run to apply changes.")
    else:
        print("DONE — see the audit report for a full change log.")
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# --direct mode
# ---------------------------------------------------------------------------

def _run_direct(instruction: str, dry_run: bool) -> None:
    """
    Parse a natural-language instruction, find the matching page(s),
    inject the instruction as high-priority context, and run a targeted update.

    Examples:
      "update Feature Registry: dark mode launched for members on 2026-05-30"
      "North Star Metrics — Q2 MAU target revised to 450k"
    """
    print(f"\nDIRECT UPDATE MODE")
    print(f"Instruction: {instruction}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}\n")

    matched_pages = _match_pages_to_instruction(instruction)

    if not matched_pages:
        print("Could not match the instruction to any tracked page.")
        print("Tracked pages:", ", ".join(p["title"] for p in PAGES))
        sys.exit(1)

    phase2_changes: list[dict] = []
    phase3_changes: list[dict] = []
    audit_results: list[dict] = []

    for page_cfg in matched_pages:
        print(f"  → Targeting: {page_cfg['title']}")
        result = run_targeted_audit(page_cfg, extra_context=instruction)
        audit_results.append(result)

        if result.get("error"):
            print(f"    ERROR: {result['error']}")
            continue

        print(f"    Status: {result['status']}")
        fills = result.get("analysis", {}).get("fills", [])
        high = [f for f in fills if f.get("confidence") == "HIGH"]
        print(f"    Proposed fills: {len(fills)} total, {len(high)} HIGH confidence")

    phase2_changes = run_panel_updates(audit_results, dry_run)
    phase3_changes = run_gap_fills(audit_results, dry_run)
    generate_report(audit_results, phase2_changes, phase3_changes, dry_run)

    print("\n" + "=" * 70)
    if dry_run:
        print("DRY-RUN COMPLETE — no Confluence pages were modified.")
    else:
        print("DIRECT UPDATE COMPLETE — see the audit report for changes.")
    print("=" * 70 + "\n")


def _match_pages_to_instruction(instruction: str) -> list[dict]:
    """
    Find pages whose title or keywords match the instruction text.
    Returns a list (usually 1) of page config dicts.
    """
    instr_lower = instruction.lower()
    matches: list[dict] = []

    for page in PAGES:
        title_lower = page["title"].lower()
        # Direct title match
        if title_lower in instr_lower or any(
            word in instr_lower for word in title_lower.split()
        ):
            matches.append(page)
            continue
        # Keyword match
        if any(kw.lower() in instr_lower for kw in page.get("keywords", [])):
            matches.append(page)

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[dict] = []
    for p in matches:
        if p["id"] not in seen:
            seen.add(p["id"])
            unique.append(p)

    return unique


# ---------------------------------------------------------------------------
# --listen mode (Slack bot)
# ---------------------------------------------------------------------------

# Module-level store for the most recent audit results (used by bot "status" command)
_last_audit_results: list[dict] = []


def _run_listen_mode(dry_run: bool) -> None:
    """Start the Slack bot and block until Ctrl+C."""
    from src.slack_bot import start_bot

    print(f"\nSLACK BOT MODE — Spring Health Confluence Maintenance Agent")
    print(f"Mode  : {'DRY-RUN (read-only)' if dry_run else 'LIVE'}")
    print(f"Date  : {TODAY}")
    print("Connecting to Slack...\n")

    thread = start_bot(on_command=lambda cmd, page, instr, user: _handle_bot_command(
        cmd, page, instr, user, dry_run
    ))

    if not thread:
        sys.exit(1)

    print("Bot is running. Send a DM on Slack to interact.")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBot stopped.")


def _handle_bot_command(
    command: str, page_name: str, instruction: str, user: str, dry_run: bool
) -> str:
    """
    Called by the Slack bot when a command is received.
    Returns a Slack-formatted reply.
    """
    global _last_audit_results

    if command == "status":
        if _last_audit_results:
            return summarize_audit_for_slack(_last_audit_results)
        return (
            "_No audit has run yet this session._\n"
            "Run `python main.py --phase 1` or say `check <page name>` to audit a page."
        )

    if command == "list":
        lines = ["*Tracked pages:*\n"]
        for p in PAGES:
            rule_icon = "⚪" if p["rule"] == "SKIP" else "🔵"
            lines.append(f"{rule_icon} [{p['level']}] {p['title']}")
        return "\n".join(lines)

    if command == "check":
        matched = _match_pages_to_instruction(page_name)
        if not matched:
            all_titles = "\n".join(f"• {p['title']}" for p in PAGES)
            return f"Couldn't find a page matching *{page_name}*. Tracked pages:\n{all_titles}"

        results = []
        for page_cfg in matched[:2]:  # cap at 2 to keep response fast
            result = run_targeted_audit(page_cfg, extra_context="")
            _last_audit_results = [
                r for r in _last_audit_results if r["page"]["id"] != page_cfg["id"]
            ] + [result]
            results.append(result)

        return summarize_audit_for_slack(results)

    if command == "update":
        matched = _match_pages_to_instruction(page_name or instruction)
        if not matched:
            return (
                f"Couldn't match *{page_name}* to a tracked page.\n"
                "Try: `list` to see all tracked pages."
            )

        reply_lines: list[str] = []
        for page_cfg in matched[:2]:
            result = run_targeted_audit(page_cfg, extra_context=instruction)
            _last_audit_results = [
                r for r in _last_audit_results if r["page"]["id"] != page_cfg["id"]
            ] + [result]

            fills = result.get("analysis", {}).get("fills", [])
            high = [f for f in fills if f.get("confidence") == "HIGH"]
            medium = [f for f in fills if f.get("confidence") == "MEDIUM"]
            status = result.get("status", "?")

            if result.get("error"):
                reply_lines.append(f"❌ *{page_cfg['title']}*: fetch error — {result['error']}")
                continue

            if high and not dry_run:
                run_panel_updates([result], dry_run=False)
                run_gap_fills([result], dry_run=False)
                reply_lines.append(
                    f"✅ *{page_cfg['title']}* updated — "
                    f"{len(high)} fill(s) applied from your context."
                )
            elif high:
                reply_lines.append(
                    f"🟡 *{page_cfg['title']}* (dry-run) — "
                    f"{len(high)} HIGH-confidence fill(s) ready. "
                    f"Re-run without dry-run to apply."
                )
            elif medium:
                reply_lines.append(
                    f"🟡 *{page_cfg['title']}* — status: {status}. "
                    f"{len(medium)} MEDIUM-confidence suggestion(s) — "
                    f"manual review needed."
                )
            else:
                reply_lines.append(
                    f"ℹ️ *{page_cfg['title']}* — status: {status}. "
                    f"No auto-fillable gaps found. Your context has been noted."
                )

        return "\n".join(reply_lines) if reply_lines else "No matching pages found."

    return f"Unknown command: {command}"


# ---------------------------------------------------------------------------
# Lightweight fetch (phase 1 skipped)
# ---------------------------------------------------------------------------

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
