# How the Confluence Maintenance Agent Works

A plain-language walkthrough of what this tool does, what it changes, and what it intentionally leaves alone.

---

## What this tool is

A Python CLI that runs against Spring Health's **PO2 Confluence space** (Product Operations). It reads a fixed list of 11 pages, uses Claude to evaluate their content quality, and writes two types of changes back to Confluence: status panels and gap fills.

It is **not a scraper, not a sync tool, and not a bulk editor**. It touches exactly the pages in its registry and nothing else.

---

## The 11 pages it targets

Defined in [src/config.py](src/config.py). Two levels, two rules:

| Page | Level | Rule |
|------|-------|------|
| Product Vision & Strategy | L1 | **SKIP** |
| Product Principles | L1 | **SKIP** |
| North Star Metrics | L1 | REVIEW |
| User Personas & Segments | L1 | REVIEW |
| Competitive Landscape | L1 | REVIEW |
| Product Glossary | L1 | REVIEW |
| Product Area Overviews | L2 | REVIEW |
| Feature Registry | L2 | REVIEW |
| Technical Constraints | L2 | REVIEW |
| Data Model Overview | L2 | REVIEW |
| Integration Map | L2 | REVIEW |

**SKIP** = body content is owned by leadership and will never be auto-edited. Panel update only.  
**REVIEW** = eligible for gap analysis and auto-fill (with confidence gates — see Phase 3).

---

## The three phases

### Phase 1 — Audit (read-only)

1. Fetches each page's full body content via the Confluence REST API.
2. Runs a CQL keyword search across five other Confluence spaces — `MX`, `PE`, `CV`, `PCS`, `ENG` — looking for pages modified since `2026-01-01` that mention the page's keywords (e.g., "north star", "KPI", "OKR" for the North Star Metrics page). Up to 8 results per page.
3. Sends the page body (first 6,000 chars) + search results (first 4,000 chars) to **Claude Sonnet** and asks it to:
   - Score the page as `CURRENT`, `PARTIAL`, `SKELETON`, or `STALE`
   - List `[TO FILL]` markers and missing fields (gaps)
   - Propose fill values with `HIGH`, `MEDIUM`, or `LOW` confidence
   - Write a short message for the status panel
4. Prints an audit summary to the terminal.

**SKIP pages are not sent to Claude.** They get a fixed "leadership-owned" panel message.

**Phase 1 writes nothing to Confluence.**

---

### Phase 2 — Info panel injection

Injects (or replaces) a colored status badge at the very top of every page's body.

The panel is a native Confluence macro (`<ac:structured-macro>`). It looks like a colored callout box with a badge:

| Page status | Panel color | Badge label |
|-------------|-------------|-------------|
| CURRENT | Green info box | CURRENT |
| PARTIAL | Yellow info box | PARTIAL |
| SKELETON | Red note box | SKELETON |
| STALE | Red warning box | STALE |
| SKIP pages | Green info box | CURRENT |

A hidden sentinel comment (`<!-- confluence-maintenance-agent-panel -->`) is embedded in the XML. On re-runs, the tool finds the sentinel and replaces the old panel in-place — it does **not** prepend a second panel or touch anything else in the body.

**Phase 2 is the only phase that touches SKIP pages** (panel update only, no body content changes).

---

### Phase 3 — Gap fills

For `REVIEW` pages only, replaces `[TO FILL]` markers in the page body with real content — but only when Claude's confidence is `HIGH`.

**Confidence levels and what happens to each:**

| Confidence | Definition | Action |
|------------|------------|--------|
| **HIGH** | Value is a verbatim quote from a search result | Auto-filled in Confluence |
| **MEDIUM** | Strongly implied by a search result, not a direct quote | Surfaced in the audit report, **never written** |
| **LOW** | Inferred — not directly sourced | Left as `[TO FILL]` |

When a `HIGH` fill is written, the value gets an inline source footnote appended:
```
<value> (Source: <Page Title> — verified 2026-05-28)
```

The fill targets the specific `[TO FILL]` marker associated with the field Claude identified, not all `[TO FILL]` markers blindly.

---

## What the tool writes to Confluence

| What | When | Pages affected |
|------|------|----------------|
| Status info panel (top of page) | Phase 2, every run | All 11 pages |
| `[TO FILL]` replacement with sourced content | Phase 3, HIGH confidence only | REVIEW pages only |

---

## What the tool never changes

- **Body content of SKIP pages** — Product Vision & Strategy and Product Principles are panel-only. Claude never analyzes them; their `[TO FILL]` markers, if any, are never touched.
- **MEDIUM or LOW confidence fills** — they appear in the audit report as suggestions for human review but are never written back.
- **Page titles** — never modified.
- **Page hierarchy or parent/child structure** — never modified.
- **Existing body content that isn't a `[TO FILL]` marker** — Phase 3 only replaces the markers; it does not rewrite, summarize, or rephrase existing text.
- **Pages outside the registry** — only the 11 hardcoded pages in `src/config.py` are ever touched. No other PO2 pages, no other spaces.
- **Source spaces** — the tool *reads* from MX, PE, CV, PCS, ENG for reference material but never writes to them.

---

## The output file

After every run, `audit_report_YYYY-MM-DD.md` is written to the project root. It contains:

- **Summary table** — pages audited, panels updated, fills applied, errors
- **Status distribution** — how many pages scored CURRENT / PARTIAL / SKELETON / STALE
- **Per-page results** — status, rationale from Claude, list of gaps found, proposed fills with confidence and source links
- **Changes made table** — every Phase 2 and Phase 3 write, with old/new values and source
- **Remaining `[TO FILL]` items** — grouped by page, with MEDIUM confidence suggestions for human review

In `--dry-run` mode, the report is still generated but the changes table shows what *would have* been written.

---

## Safety mechanisms

| Mechanism | What it protects against |
|-----------|--------------------------|
| `--dry-run` flag | Zero Confluence API write calls — full audit and report, no changes |
| SKIP rule | Leadership-owned pages never have body content modified |
| Confidence gate (HIGH only) | Low-quality or inferred content never auto-fills |
| Sentinel comment in panel XML | Re-runs replace the existing panel, never duplicate it |
| Source annotation on fills | Every auto-fill is traceable back to the exact Confluence page it came from |
| `--phase 1` flag | Run audit and generate report before committing to any writes |
| `--pages` flag | Scope a run to one or two specific page IDs for testing |

---

## Credentials required

Two environment variables must be set before running:

| Variable | What it is |
|----------|-----------|
| `CONFLUENCE_EMAIL` | Your `@springhealth.com` email |
| `CONFLUENCE_TOKEN` | Atlassian API token (from `id.atlassian.com`) |
| `ANTHROPIC_API_KEY` | Claude API key (from `console.anthropic.com`) |

---

## Recommended run order

```bash
# Step 1 — always start here: full audit, zero writes
python main.py --dry-run

# Step 2 — review audit_report_YYYY-MM-DD.md

# Step 3 — if the proposed changes look right, run live
python main.py
```

---

## What's not built yet

The README notes three planned source connectors that are not yet implemented:

1. **Google Drive** — search matching Spring Health docs
2. **Slack** — surface recent mentions from product channels
3. **Meeting notes** — extract decisions and action items

Currently the only source of fill content is other Confluence spaces (MX, PE, CV, PCS, ENG).
