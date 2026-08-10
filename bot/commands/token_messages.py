"""Shared user-facing strings for the 17lands token DM flows (/join, /link-17lands)."""

WALKTHROUGH_STEPS = (
    "1. Go to [17lands.com/history/events](https://www.17lands.com/history/events)\n"
    "2. Click the **event history** link.\n"
    "3. Copy the URL from your browser's address bar. It looks like:\n"
    "`https://www.17lands.com/user_history/abc123...` (any `?...` extras at the end are fine)\n"
    "4. Reply to this message with the full URL or just the token."
)
TOKEN_PRIVACY_NOTE = "*Your token is stored securely and only used to fetch your game stats.*"

CHECKING = "⏳ Checking your 17lands link…"
FETCHING_EVENTS = "🔄 Link verified! Pulling your 17lands drafts now..."
INVALID_FORMAT = "That doesn't look like a valid 17lands token. Please check and try again"
REJECTED = (
    "17lands didn't recognize that token. Open your [event history](https://www.17lands.com/history/events) "
    "and copy the full URL from your address bar"
)
TOKEN_IN_USE = "That 17lands token is already linked to another Discord account"
DMS_DISABLED = "⚠️ Your DMs are blocked. Enable DMs from server members, then try again"
