from __future__ import annotations

from collections.abc import Mapping

REQUIRED_ENV_NAMES = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "GHL_API_KEY",
    "GHL_LOCATION_ID",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "AGENTMAIL_API_KEY",
    "CLICKUP_API_TOKEN",
    "CLICKUP_WORKSPACE_ID",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "TELEGRAM_BOT_TOKEN",
)


def audit_env(env: Mapping[str, str | None]) -> dict[str, str]:
    """Return present/missing only. Never return secret values."""
    return {name: "present" if env.get(name) else "missing" for name in REQUIRED_ENV_NAMES}
