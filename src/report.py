"""
Markdown audit report generator.
Writes audit_report_YYYY-MM-DD.md and returns the content string.
"""

from datetime import datetime

from src.config import SPACE_ID, SPACE_KEY, TODAY
from src.confluence import build_page_url


def generate_report(
    audit_results: list[dict],
    phase2_changes: list[dict],
    phase3_changes: list[dict],
    dry_run: bool,
) -> str:
    """Build and write the markdown report. Returns the report string."""
    content = _build_report(audit_results, phase2_changes, phase3_changes, dry_run)
    filename = f"audit_report_{TODAY}.md"
    with open(filename, "w") as fh:
        fh.write(content)
    print(f"\n  Report written: {filename}")
    return content


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _build_report(
    audit_results: list[dict],
    phase2_changes: list[dict],
    phase3_changes: list[dict],
    dry_run: bool,
) -> str:
    total = len(audit_results)
    skipped_leadership = sum(1 for r in audit_results if r["page"]["rule"] == "SKIP")
    errors = sum(1 for r in audit_results if r.get("error"))
    panels_updated = sum(
        1 for c in phase2_changes if "FAILED" not in c.get("new_value", "")
    )
    high_fills = [c for c in phase3_changes if c.get("confidence") == "HIGH" and "NOT WRITTEN" not in c.get("new_value","")]
    medium_fills = [c for c in phase3_changes if c.get("confidence") == "MEDIUM"]

    status_counts: dict[str, int] = {}
    for r in audit_results:
        s = r.get("status", "?")
        status_counts[s] = status_counts.get(s, 0) + 1

    mode_note = " *(DRY-RUN — no writes made)*" if dry_run else ""
    lines: list[str] = [
        f"# Confluence Maintenance Audit Report{mode_note}",
        f"",
        f"**Date:** {TODAY}  ",
        f"**Space:** {SPACE_KEY} (ID: {SPACE_ID})  ",
        f"**Mode:** {'DRY-RUN' if dry_run else 'LIVE'}  ",
        f"",
        "## Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Pages audited | {total} |",
        f"| Info panels updated | {panels_updated if not dry_run else f'0 ({total - skipped_leadership - errors} planned)'} |",
        f"| Pages skipped (leadership) | {skipped_leadership} |",
        f"| Fetch errors | {errors} |",
        f"| Gaps filled — HIGH confidence | {len(high_fills) if not dry_run else 0} |",
        f"| Gaps surfaced for review (MEDIUM) | {len(medium_fills)} |",
        "",
        "## Status Distribution",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"| {status} | {count} |")

    lines += ["", "## Page-by-Page Results", ""]

    for result in audit_results:
        lines += _page_section(result)

    # Changes table
    all_changes = phase2_changes + phase3_changes
    if all_changes:
        lines += [
            "## Changes Made",
            "",
            "| Phase | Page | Field | Old Value | New Value | Confidence | Source |",
            "|-------|------|-------|-----------|-----------|------------|--------|",
        ]
        for c in all_changes:
            url = build_page_url(c.get("page_id", ""))
            page_link = f"[{c['page']}]({url})"
            field = _escape_pipe(c.get("field", ""))
            old = _escape_pipe(str(c.get("old_value", ""))[:60])
            new = _escape_pipe(str(c.get("new_value", ""))[:60])
            conf = c.get("confidence", "N/A")
            src = _escape_pipe(str(c.get("source", "")))
            lines.append(
                f"| Ph{c.get('phase','?')} | {page_link} | {field} "
                f"| {old} | {new} | {conf} | {src} |"
            )
        lines.append("")

    # Remaining gaps
    lines += [
        "## Remaining [TO FILL] Items",
        "",
        "Items not auto-filled (LOW / MEDIUM confidence, or not found in search).",
        "",
    ]
    for result in audit_results:
        if result.get("error") or result["page"]["rule"] == "SKIP":
            continue
        analysis = result.get("analysis", {})
        remaining_gaps = analysis.get("gaps", [])
        medium_fills_for_page = [
            f for f in analysis.get("fills", []) if f.get("confidence") in ("LOW", "MEDIUM")
        ]
        if remaining_gaps or medium_fills_for_page:
            url = build_page_url(result["page"]["id"])
            lines += [f"### [{result['fetched_title']}]({url})", ""]
            for g in remaining_gaps:
                lines.append(f"- [ ] {g}")
            for f in medium_fills_for_page:
                conf = f.get("confidence", "?")
                val = str(f.get("value", ""))[:80]
                src = f.get("source_name", "?")
                lines.append(f"- [ ] **{f['field']}** — suggested: _{val}_ ({conf} confidence, source: {src})")
            lines.append("")

    lines += [
        "---",
        f"*Generated by confluence-maintenance-agent · {datetime.now().isoformat(timespec='seconds')}*",
    ]

    return "\n".join(lines)


def _page_section(result: dict) -> list[str]:
    page_cfg = result["page"]
    title = page_cfg["title"]
    pid = page_cfg["id"]
    rule = page_cfg["rule"]
    level = page_cfg["level"]
    status = result.get("status", "ERROR")
    analysis = result.get("analysis", {})
    url = build_page_url(pid)

    lines: list[str] = [
        f"### [{title}]({url})",
        f"**Level:** {level} | **Rule:** {rule} | **Status:** `{status}`",
        "",
    ]

    if result.get("error"):
        lines += [f"> ⚠ Fetch error: {result['error']}", ""]
        return lines

    rationale = analysis.get("rationale", "")
    if rationale:
        lines += [f"_{rationale}_", ""]

    gaps = analysis.get("gaps", [])
    if gaps:
        lines += ["**Gaps found:**", ""]
        for g in gaps:
            lines.append(f"- {g}")
        lines.append("")

    fills = analysis.get("fills", [])
    if fills:
        lines += [
            "**Proposed fills:**",
            "",
            "| Field | Value | Confidence | Source |",
            "|-------|-------|------------|--------|",
        ]
        for f in fills:
            src_name = f.get("source_name", "?")
            src_url = f.get("source_url")
            src_cell = f"[{src_name}]({src_url})" if src_url else src_name
            conf = f.get("confidence", "?")
            val = _escape_pipe(str(f.get("value", ""))[:80])
            field = _escape_pipe(str(f.get("field", "")))
            lines.append(f"| {field} | {val} | **{conf}** | {src_cell} |")
        lines.append("")

    if rule == "SKIP":
        lines += ["> SKIP — awaiting leadership input. Info panel updated only.", ""]

    return lines


def _escape_pipe(s: str) -> str:
    return s.replace("|", "\\|")
