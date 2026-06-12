# Confluence Maintenance Agent

Keeps Spring Health's Product Operations (PO2) Confluence space accurate and up to date by pulling signals from **Confluence, Slack, Jira, and Granola meeting notes**, and by accepting direct update instructions over Slack DMs.

Targets L1 (Product Foundations) and L2 (Domain Context) pages.

---

## What it does

### Sources it reads from

| Source | What it looks for | Credential needed |
|--------|-------------------|-------------------|
| Confluence | Recent pages in MX, PE, CV, PCS, ENG spaces | `CONFLUENCE_TOKEN` (already required) |
| Slack | Channel messages mentioning each page's keywords | `SLACK_BOT_TOKEN` |
| Jira | Open tickets updated in the last 30 days | `CONFLUENCE_TOKEN` (same Atlassian token) |
| Granola | Meeting notes via local app API or export folder | None (app must be running) |
| Direct input | Explicit context via `--direct` CLI or Slack DM | — |

All sources are optional and fail gracefully — the agent runs with whatever is configured.

### Three-phase pipeline

| Phase | Action | SKIP pages | REVIEW pages |
|-------|--------|------------|--------------|
| 1 — Audit | Fetch pages + multi-source context + Claude gap analysis | Scored, no fills | Full gap + fill analysis |
| 2 — Panels | Inject status panel at top of every page | Panel only | Panel only |
| 3 — Fills | Replace `[TO FILL]` markers | Never touched | HIGH confidence auto-filled |

**Safety rules:**
- `SKIP` pages (Product Vision & Strategy, Product Principles) never have body content modified.
- `MEDIUM` confidence fills are surfaced in the report but never written automatically.
- `LOW` confidence fills are left as `[TO FILL]`.
- `--dry-run` makes zero Confluence API write calls.
- `direct_input` context (from `--direct` or Slack DMs) is treated as HIGH confidence.

---

## Setup

### 1. Install Python 3.11+

```bash
# macOS — Homebrew
brew install python@3.11
```

### 2. Create a virtual environment

```bash
cd confluence-maintenance-agent
python3.11 -m venv .venv
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

**Minimum required:**
- `CONFLUENCE_EMAIL` + `CONFLUENCE_TOKEN` — Atlassian API token from [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens)
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com/settings/keys)

**Slack (enables channel search + bot DM mode):**
- Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps)
- Bot Token Scopes: `channels:history`, `channels:read`, `groups:history`, `groups:read`, `im:history`, `im:read`, `im:write`, `chat:write`
- For `--listen` mode: enable Socket Mode and generate an App-Level Token with `connections:write`
- Set `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in `.env`
- Invite the bot to each channel in `SLACK_CHANNELS` with `/invite @your-bot`

---

## Usage

### Batch audit (recommended starting point)

```bash
# Full audit across all sources, zero writes, generates report
python main.py --dry-run

# After reviewing the report, run live
python main.py

# Individual phases
python main.py --phase 1        # audit + report only
python main.py --phase 2        # status panels only
python main.py --phase 3        # gap fills only

# Restrict to specific pages
python main.py --dry-run --pages 3890610497 3896967190
```

### Direct update (one-shot injection)

Feed an explicit change directly into the agent without waiting for the next scheduled run:

```bash
python main.py --direct "update Feature Registry: dark mode launched for members on 2026-05-30"
python main.py --direct "North Star Metrics: Q2 MAU target revised to 450k per Thursday OKR review"
python main.py --dry-run --direct "update Competitive Landscape: Lyra Health raised Series D"
```

The agent matches the instruction to the right page(s), injects it as HIGH-confidence context, runs a targeted audit, and applies fills.

### Slack bot (persistent listener)

```bash
# Start the bot — blocks until Ctrl+C
python main.py --listen

# Dry-run mode (reads Slack DMs, never writes Confluence)
python main.py --listen --dry-run
```

Once running, DM the bot on Slack:

| Command | What it does |
|---------|-------------|
| `update Feature Registry: dark mode launched 2026-05-30` | Injects context, runs targeted update |
| `check Competitive Landscape` | Runs a fresh audit on that page |
| `status` | Returns the last audit summary |
| `list` | Lists all 11 tracked pages |
| `help` | Shows usage |

---

## Project structure

```
confluence-maintenance-agent/
├── main.py                   # CLI entry point (--dry-run, --phase, --direct, --listen)
├── requirements.txt
├── .env.example              # copy to .env, fill in credentials
├── .gitignore
└── src/
    ├── config.py             # Page registry, Slack channels, Jira projects, constants
    ├── confluence.py         # Confluence REST API client
    ├── slack_connector.py    # Slack channel search
    ├── jira_connector.py     # Jira ticket search (uses Atlassian token)
    ├── granola_connector.py  # Granola meeting notes (local API + export folder)
    ├── slack_bot.py          # Slack Bolt bot for DM-driven updates
    ├── claude_ai.py          # Multi-source Claude prompt + response parsing
    ├── audit.py              # Phase 1: fetch, gather all sources, score
    ├── fills.py              # Phase 2: panels / Phase 3: gap fills
    ├── panels.py             # Confluence panel XML builder
    └── report.py             # Markdown audit report generator
```

---

## Page registry

Defined in [src/config.py](src/config.py).

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

---

## Granola integration

The Granola desktop app exposes a local HTTP API on port 1618. The agent queries it automatically when Granola is running — no configuration needed.

If you'd rather not keep Granola open, export notes from Granola and set:
```
GRANOLA_EXPORT_DIR=/path/to/your/exports
```
The agent will scan that folder for `.md` and `.json` files.
