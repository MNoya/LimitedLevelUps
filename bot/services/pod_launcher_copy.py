"""All player-facing copy for the Daily Pod Launcher and its rolling-signup surfaces.

One place to edit launcher wording. Genuinely cross-surface strings (the Format Preference button
label, shared with the roster reminder) stay in `bot/commands/messages.py`; custom_ids and layout
constants stay beside the code that uses them.

Plain declarative microcopy: name the real thing and the real action in the plainest accurate word,
literal compositional verbs, no phrasal verbs or idioms, no em dashes, no marketing register.
"""
from __future__ import annotations

from bot.commands.messages import MSG_PREFERENCE_LINE
from bot.services import pod_format_interest as fi


POLL_TITLE = "Daily Pod Launcher"
POLL_INTRO = (
    "### Sign up for any time below\n"
    "• Pod event thread opens when it reaches **{threshold} players**\n"
    "• The Draftmancer lobby opens **{lead} minutes before** the start time"
)
POLL_FORMATS = (
    "### Format 1: {main}\n"
    "### Format 2: {second}\n"
    "• Sign up for both to play in the first pod to fill"
)
POLL_FORMAT_SINGLE = "### Format: {main}"
POLL_CLOSED_LABEL = "🔒 Signups Closed"
ARCHIVE_INTRO = "### On This Day"
MARKER_CLOSED = "Closed"
FINISHED_MARK = "🏆"
PLAYING_MARK = "⚔️"
SECTION_NEXT = "**Next**"
NEXT_EMOJI = "chordoHello"
MSG_POLL_INACTIVE = "This poll is no longer active."
MSG_SLOT_CLOSED = "This slot is closed."

PLAY_AGAIN_LOVE_EMOJI = "chordo_love"
PLAY_AGAIN_INTRO = (
    "{love} Thank you for playing!\n"
    "🚀 Sign up for the next {slot} from here, same time tomorrow!"
)
PLAY_AGAIN_BUTTON = "Play Again"
PLAY_AGAIN_CONFIRM = "✅ Added to the next {slot}\nDraft scheduled for <t:{unix}:F>"

INTEREST_PLACEHOLDER = "Select your Format Preference"
INTEREST_DESC_FLASHBACK = "Any Past Set, Rank Your Favorites"
INTEREST_DESC_CUBE = "Choose from the server's cubes"
MSG_INTEREST_PROMPT = (
    "### Choose what you would prefer to draft\n"
    "**Save** your preference, or **Confirm** to also join that time slot today"
)
MSG_INTEREST_SAVED = f"### ✨ Saved\n{MSG_PREFERENCE_LINE}"
MSG_SLOT_ADDED = "✅ Added to {name}"
MSG_SLOT_REMOVED = "❌ Removed from {name}"
SAVE_BUTTON_LABEL = "Save"
SAVE_BUTTON_EMOJI = "💾"
CONFIRM_SLOT_LABEL = "Confirm {name}"
RANK_BUTTON_LABEL = "Rank Sets"
RANK_BUTTON_EMOJI = "📊"
RANK_MODAL_TITLE = "Rank Flashback Sets"
RANK_MODAL_FIELD = "Set Codes"
RANK_MODAL_PLACEHOLDER = "e.g. XXX YYY NEO"
RANK_MODAL_EXPLAINER = (
    f"Set your Flashback preference, best first, **up to {fi.FLASHBACK_RANKING_MAX} sets**\n\nWhen a pod opens a "
    "**Format Vote**, your sets are added to the poll options"
)
MSG_RANK_EMPTY = "No sets ranked"
CUBE_SELECT_PLACEHOLDER = "Select Cubes"
