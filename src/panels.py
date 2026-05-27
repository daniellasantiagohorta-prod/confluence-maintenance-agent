"""
Confluence Storage Format (XHTML) info-panel builder and body injector.
"""

# sentinel comment lets us find and replace the panel on re-runs without
# duplicating it or touching other body content
PANEL_SENTINEL = "<!-- confluence-maintenance-agent-panel -->"

# status -> (macro_name, badge_colour, badge_title)
_PANEL_TEMPLATES: dict[str, tuple[str, str, str]] = {
    "CURRENT":  ("info",    "Green",  "CURRENT"),
    "PARTIAL":  ("info",    "Yellow", "PARTIAL"),
    "SKELETON": ("note",    "Red",    "SKELETON"),
    "STALE":    ("warning", "Red",    "STALE"),
}
_FALLBACK = ("info", "Yellow", "PARTIAL")


def build_info_panel(status: str, message: str) -> str:
    """Return a Confluence storage-format panel XML string, prefixed with the sentinel."""
    macro_name, badge_colour, badge_title = _PANEL_TEMPLATES.get(status, _FALLBACK)
    safe_message = message.replace("&", "&amp;")

    return (
        f"{PANEL_SENTINEL}\n"
        f'<ac:structured-macro ac:name="{macro_name}" '
        f'ac:schema-version="1" ac:macro-id="maintenance-status-panel">\n'
        f"  <ac:rich-text-body>\n"
        f'    <ac:structured-macro ac:name="status">\n'
        f'      <ac:parameter ac:name="title">{badge_title}</ac:parameter>\n'
        f'      <ac:parameter ac:name="colour">{badge_colour}</ac:parameter>\n'
        f"    </ac:structured-macro>\n"
        f"    &nbsp;{safe_message}\n"
        f"  </ac:rich-text-body>\n"
        f"</ac:structured-macro>"
    )


def inject_panel_into_body(current_body: str, panel_xml: str) -> str:
    """
    Replace the existing agent panel if present, or prepend a new one.
    All other page content is left untouched.
    """
    if PANEL_SENTINEL in current_body:
        start = current_body.index(PANEL_SENTINEL)
        close_tag = "</ac:structured-macro>"
        end_search_start = start
        # Find the closing tag that matches the macro we injected
        end = current_body.find(close_tag, end_search_start)
        if end == -1:
            # Sentinel present but closing tag not found — replace from sentinel to end
            return panel_xml + "\n" + current_body[:start]
        end += len(close_tag)
        return panel_xml + "\n" + current_body[end:].lstrip("\n")
    return panel_xml + "\n" + current_body
