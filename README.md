# Confluence Maintenance Agent

Audits and maintains Spring Health's Product Operations (PO2) Confluence space.
Targets L1 (Product Foundations) and L2 (Domain Context) pages.

## What it does

| Phase | Action | SKIP pages | REVIEW pages |
|-------|--------|------------|--------------|
| 1 — Audit | Fetch pages + Claude gap analysis | Scored, no fills | Full gap + fill analysis |
| 2 — Panels | Inject status panel at top of every page | Panel only | Panel only |
| 3 — Fills | Replace `[TO FILL]` markers | Never touched | HIGH confidence auto-filled |

**Safety rules:**
- `SKIP` pages (Product Vision & Strategy, Product Principles) never have body content modified — info panel only.
- `MEDIUM` confidence fills are surfaced in the report but never written automatically.
- `LOW` confidence fills are left as `[TO FILL]`.
- `--dry-run` makes zero Confluence API write calls.

## Setup

### 1. Install Python 3.11+

```bash
# macOS — Homebrew
brew install python@3.11
```

### 2. Create a virtual environment

```bash
cd confluence-maintenance-agent
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set credentials

```bash
cp .env.example .env
# edit .env with your real values
```

Then load them in your shell:

```bash
export $(grep -v '^#' .env | xargs)
```

Or use [direnv](https://direnv.net/) to load `.env` automatically when you `cd` into the folder.

Get credentials here:
- **Confluence token:** https://id.atlassian.com/manage-profile/security/api-tokens
- **Anthropic API key:** https://console.anthropic.com/settings/keys

## Usage

```bash
# Always start here — full audit, zero writes, generates audit_report_YYYY-MM-DD.md
python main.py --dry-run

# After reviewing the report, run live
python main.py

# Run specific phases only
python main.py --phase 1        # audit only, writes report, stops
python main.py --phase 2        # info panels only (safe)
python main.py --phase 3        # gap fills only

# Target specific pages by ID
python main.py --dry-run --pages 3890610497 3896967190
```

## Project structure

```
confluence-maintenance-agent/
├── main.py               # CLI entry point
├── requirements.txt
├── .env.example          # copy to .env, fill in credentials
├── .gitignore
├── .vscode/
│   ├── settings.json     # Python interpreter, formatter
│   └── extensions.json   # Recommended VS Code extensions
└── src/
    ├── config.py         # Page registry, constants, Claude model
    ├── confluence.py     # Confluence REST API client
    ├── claude_ai.py      # Claude gap-analysis prompt + response parsing
    ├── panels.py         # Storage-format XML panel builder + body injector
    ├── audit.py          # Phase 1: fetch, search, score
    ├── fills.py          # Phase 2: panel updates / Phase 3: gap fills
    └── report.py         # Markdown audit report generator
```

## Page registry

Pages are defined in [src/config.py](src/config.py). Add, remove, or update pages there.

| Page | ID | Level | Rule |
|------|----|-------|------|
| Product Vision & Strategy | 3891659024 | L1 | SKIP |
| North Star Metrics | 3890610497 | L1 | REVIEW |
| User Personas & Segments | 3890479561 | L1 | REVIEW |
| Product Principles | 3891233109 | L1 | SKIP |
| Competitive Landscape | 3891724617 | L1 | REVIEW |
| Product Glossary | 3891560725 | L1 | REVIEW |
| Product Area Overviews | 3898114058 | L2 | REVIEW |
| Feature Registry | 3896967190 | L2 | REVIEW |
| Technical Constraints | 3897655306 | L2 | REVIEW |
| Data Model Overview | 3897655332 | L2 | REVIEW |
| Integration Map | 3896115318 | L2 | REVIEW |

## Output

After every run, `audit_report_YYYY-MM-DD.md` is written to the project root with:
- Per-page status scores and gap lists
- Proposed fills with confidence levels and sources
- Full change log (phase 2 panels + phase 3 fills)
- Remaining `[TO FILL]` items grouped by page

## Phase 2 expansion (coming)

Additional source connectors planned:
1. **Google Drive** — search for matching Spring Health docs
2. **Slack** — surface recent mentions from `#product-ops`, `#member-growth-team`, etc.
3. **Meeting notes** — extract decisions and action items from Drive meeting notes

Each new source will apply a confidence penalty before any auto-fill is allowed.
