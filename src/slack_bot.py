"""
Slack bot — accept DMs and trigger targeted Confluence updates.

Uses Slack Bolt with Socket Mode so no public URL is required.
The bot runs in a background thread alongside the main agent loop.

Setup:
  1. Create a Slack App at https://api.slack.com/apps
  2. Enable Socket Mode, generate an App-Level Token (xapp-...) with
     connections:write scope → set as SLACK_APP_TOKEN
  3. Under "Event Subscriptions" subscribe to bot events: message.im
  4. Under "OAuth & Permissions" add Bot Token Scopes:
       channels:history, channels:read, chat:write, groups:history,
       groups:read, im:history, im:read, im:write
  5. Install app to workspace, copy Bot User OAuth Token → SLACK_BOT_TOKEN

Commands the bot understands (sent as DMs):
  help                          — show usage
  status                        — last audit summary
  update <page>: <what changed> — flag a page with new context and trigger update
  check <page>                  — run a targeted audit on one page
  list                          — list tracked pages
"""

import os
import re
import threading
from typing import Callable, Optional

try:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    SLACK_BOLT_AVAILABLE = True
except ImportError:
    SLACK_BOLT_AVAILABLE = False


# Type alias for the callback passed in from main.py
# Signature: (command, page_name, instruction, user) -> reply_text
UpdateCallback = Callable[[str, str, str, str], str]

_HELP_TEXT = """\
*Confluence Maintenance Agent* — commands:

• `update <page name>: <what changed>` — add context and trigger an update
• `check <page name>` — run a fresh audit on one page
• `list` — show all tracked pages
• `status` — show the last audit summary
• `help` — this message

*Examples:*
`update Feature Registry: dark mode launched for members on 2026-05-30`
`update North Star Metrics: Q2 MAU target revised to 450k in Thursday's OKR review`
`check Competitive Landscape`
"""


def start_bot(on_command: UpdateCallback) -> Optional[threading.Thread]:
    """
    Start the Slack bot in a daemon background thread.

    on_command(command, page_name, instruction, user) -> str
        command: "update" | "check" | "status" | "list"
        Returns a Slack-formatted reply string.

    Returns the thread (or None if prerequisites are missing).
    """
    if not SLACK_BOLT_AVAILABLE:
        print(
            "  [bot] slack-bolt not installed — run: pip install 'slack-bolt>=1.18'",
            flush=True,
        )
        return None

    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")

    if not bot_token:
        print("  [bot] SLACK_BOT_TOKEN not set — bot not started", flush=True)
        return None
    if not app_token:
        print("  [bot] SLACK_APP_TOKEN not set — bot not started", flush=True)
        return None

    app = App(token=bot_token)

    @app.event("message")
    def handle_message(event, say):
        # Only handle direct messages (not channel messages)
        if event.get("channel_type") != "im":
            return
        # Ignore bot messages and message_changed subtypes
        if event.get("subtype") or event.get("bot_id"):
            return

        text = (event.get("text") or "").strip()
        user = event.get("user", "unknown")

        if not text:
            return

        _dispatch(text, user, say, on_command)

    handler = SocketModeHandler(app, app_token)
    thread = threading.Thread(target=handler.start, daemon=True, name="slack-bot")
    thread.start()
    print("  [bot] Slack bot started (Socket Mode) — DM the bot to send updates", flush=True)
    return thread


# ---------------------------------------------------------------------------
# Command dispatcher
# ---------------------------------------------------------------------------

def _dispatch(text: str, user: str, say: Callable, on_command: UpdateCallback) -> None:
    cmd = text.strip().lower()

    if cmd in ("help", "?", "hi", "hello"):
        say(_HELP_TEXT)
        return

    if cmd == "status":
        say("_Checking last audit status…_")
        reply = on_command("status", "ALL", "", user)
        say(reply or "_No audit data available yet. Run `python main.py --phase 1` first._")
        return

    if cmd == "list":
        reply = on_command("list", "ALL", "", user)
        say(reply)
        return

    # "update <page>: <instruction>"  or  "update <page> with: <instruction>"
    update_match = re.match(
        r"(?:update|flag|refresh|sync)\s+(.+?)(?:\s*[,:]\s*|\s+with[:\s]+)(.+)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if update_match:
        page_name = update_match.group(1).strip().rstrip(":,")
        instruction = update_match.group(2).strip()
        say(f"Got it! Processing update for *{page_name}* with your context…")
        reply = on_command("update", page_name, instruction, user)
        say(reply)
        return

    # "check <page>"
    check_match = re.match(
        r"(?:check|audit|review|scan)\s+(.+)", text, re.IGNORECASE
    )
    if check_match:
        page_name = check_match.group(1).strip()
        say(f"Auditing *{page_name}*…")
        reply = on_command("check", page_name, "", user)
        say(reply)
        return

    # Unknown command — friendly fallback
    say(
        f"I'm not sure how to parse that. Try:\n"
        f"`update Feature Registry: <what changed>`\n"
        f"or type `help` to see all commands."
    )
