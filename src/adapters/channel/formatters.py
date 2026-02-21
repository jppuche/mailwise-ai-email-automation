"""SlackBlockKitFormatter — pure local transformation of RoutingPayload to Slack blocks.

try-except D8: All logic uses conditionals only. No I/O, no try/except.
"""

from __future__ import annotations

from src.adapters.channel.schemas import RoutingPayload
from src.core.config import get_settings

# ---------------------------------------------------------------------------
# Priority constants (Cat 3 pre-mortem: no magic strings)
# ---------------------------------------------------------------------------

PRIORITY_COLORS: dict[str, str] = {
    "urgent": "#E01E5A",  # Slack red
    "normal": "#36C5F0",  # Slack blue
    "low": "#9BA3AF",  # grey
}

PRIORITY_EMOJIS: dict[str, str] = {
    "urgent": ":red_circle:",
    "normal": ":large_blue_circle:",
    "low": ":white_circle:",
}


class SlackBlockKitFormatter:
    """Transforms RoutingPayload into a Slack Block Kit structure.

    Pure local computation — no I/O, no side effects, no try/except.
    If RoutingPayload is invalid, Pydantic has already raised before this is called.
    """

    def build_blocks(self, payload: RoutingPayload) -> list[dict[str, object]]:
        """Build Slack Block Kit blocks from a RoutingPayload.

        Preconditions:
          - ``payload`` is a valid ``RoutingPayload`` (Pydantic validated).
          - ``payload.priority`` is one of "urgent", "normal", "low".

        Guarantees:
          - Returns exactly 4 blocks: header, section (fields), context, actions.
          - ``assigned_to=None`` renders as "Unassigned".
          - Subject truncated to ``channel_subject_max_length`` (default 100).
          - Snippet truncated to ``channel_snippet_length`` (default 150).

        Errors raised: None (pure computation).

        Errors silenced: None.
        """
        settings = get_settings()
        emoji = PRIORITY_EMOJIS.get(payload.priority, ":white_circle:")
        priority_label = payload.priority.capitalize()
        subject = payload.subject[: settings.channel_subject_max_length]
        snippet = payload.snippet[: settings.channel_snippet_length]

        sender_text = (
            f"{payload.sender.name} <{payload.sender.email}>"
            if payload.sender.name
            else payload.sender.email
        )
        assigned_text = payload.assigned_to if payload.assigned_to is not None else "Unassigned"

        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} [{payload.priority.upper()}] {subject}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*From:*\n{sender_text}"},
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*Classification:*\n"
                            f"{payload.classification.action} / {payload.classification.type}"
                        ),
                    },
                    {"type": "mrkdwn", "text": f"*Priority:*\n{priority_label}"},
                    {"type": "mrkdwn", "text": f"*Assigned to:*\n{assigned_text}"},
                ],
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": snippet}],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View in Dashboard"},
                        "url": payload.dashboard_link,
                        "style": "primary",
                    }
                ],
            },
        ]
