"""
Slack connector — search channels for recent mentions of tracked topics.

Setup:
  1. Create a Slack App at https://api.slack.com/apps
  2. Under "OAuth & Permissions" add Bot Token Scopes:
       channels:history, channels:read, groups:history, groups:read,
       im:history, im:read, mpim:history, mpim:read
  3. Install the app to your workspace, copy the Bot User OAuth Token
  4. Invite the bot to each channel in SLACK_CHANNELS:
       /invite @your-bot-name
  5. Set SLACK_BOT_TOKEN in your .env

Optional: For bot DM mode (--listen), also set:
  - SLACK_APP_TOKEN (Socket Mode app-level token starting with xapp-)
    Under "Socket Mode" in your app settings, enable it and generate a token.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    SLACK_SDK_AVAILABLE = True
except ImportError:
    SLACK_SDK_AVAILABLE = False


def search_slack_channels(
    keywords: list[str],
    channels: list[str],
    days_back: int = 14,
) -> str:
    """
    Search Slack channels for recent messages mentioning any of the keywords.
    Returns formatted text for use as Claude context.

    Falls back gracefully if slack-sdk is not installed or credentials are missing.
    """
    if not SLACK_SDK_AVAILABLE:
        return "(slack-sdk not installed — run: pip install slack-sdk)"

    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        return "(SLACK_BOT_TOKEN not set — Slack source skipped)"

    client = WebClient(token=token)
    oldest = str((datetime.now() - timedelta(days=days_back)).timestamp())

    all_sections: list[str] = []

    for channel_name in channels:
        channel_id = _resolve_channel_id(client, channel_name)
        if not channel_id:
            continue

        messages = _fetch_messages(client, channel_id, oldest)
        relevant = _filter_by_keywords(messages, keywords)

        if not relevant:
            continue

        section_lines = [f"--- #{channel_name}"]
        for msg in relevant[:6]:  # cap at 6 per channel
            ts = datetime.fromtimestamp(float(msg.get("ts", 0))).strftime("%Y-%m-%d")
            text = _clean_text(msg.get("text", ""))[:400]
            section_lines.append(f"[{ts}] {text}")

        all_sections.append("\n".join(section_lines))

    return "\n\n".join(all_sections) if all_sections else "(no relevant Slack messages found)"


def get_thread_messages(channel_id: str, thread_ts: str) -> list[dict]:
    """Fetch all replies in a thread — used by the Slack bot for context."""
    if not SLACK_SDK_AVAILABLE:
        return []
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        return []
    client = WebClient(token=token)
    try:
        resp = client.conversations_replies(channel=channel_id, ts=thread_ts)
        return resp.get("messages", [])
    except SlackApiError:
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_channel_cache: dict[str, Optional[str]] = {}


def _resolve_channel_id(client: WebClient, channel_name: str) -> Optional[str]:
    name = channel_name.lstrip("#")
    if name in _channel_cache:
        return _channel_cache[name]

    try:
        cursor = None
        while True:
            kwargs = {"types": "public_channel,private_channel", "limit": 1000}
            if cursor:
                kwargs["cursor"] = cursor
            resp = client.conversations_list(**kwargs)
            for ch in resp.get("channels", []):
                if ch.get("name") == name:
                    _channel_cache[name] = ch["id"]
                    return ch["id"]
            meta = resp.get("response_metadata", {})
            cursor = meta.get("next_cursor")
            if not cursor:
                break
    except SlackApiError:
        pass

    _channel_cache[name] = None
    return None


def _fetch_messages(
    client: WebClient, channel_id: str, oldest: str
) -> list[dict]:
    """Fetch up to 200 recent messages from a channel."""
    try:
        resp = client.conversations_history(
            channel=channel_id, oldest=oldest, limit=200
        )
        return resp.get("messages", [])
    except SlackApiError:
        return []


def _filter_by_keywords(messages: list[dict], keywords: list[str]) -> list[dict]:
    lower_kws = [kw.lower() for kw in keywords]
    return [
        m for m in messages
        if any(kw in m.get("text", "").lower() for kw in lower_kws)
        and m.get("subtype") is None  # skip joins, leaves, bot_messages without text
    ]


def _clean_text(text: str) -> str:
    """Strip Slack user/channel mention tokens for readability."""
    import re
    text = re.sub(r"<@U[A-Z0-9]+>", "@user", text)
    text = re.sub(r"<#C[A-Z0-9]+\|([^>]+)>", r"#\1", text)
    text = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    return text.strip()
