"""Every user-facing string in a pod's reminder timeline, in one place so the voice stays aligned.

A pod hits these in order: the recruiting nudge across its states, the launcher slot fire ping, the
roster reminder, the lobby-open post, and the fired record. The inline reminder lines share one shape:

    {hello}{name}<t:{unix}:R> {state} {manat} [**{cta}**]({url})

The manat emoji separates the status from the action link. Builders in pod_schedule.py,
pod_daily_poll.py and pod_draft_reminder.py format these constants; new reminder copy belongs here, next
to its siblings, not back in those modules. A line naming a pod takes an already bold `{name}` because
`pod_schedule.render_pod_name` places the format symbol around it.
"""

RECRUITING_BELOW_FLOOR = (
    "{hello}{name}<t:{unix}:R> needs **{to_floor} more player{plural}** to fire a Team Draft "
    "{manat} [**Sign up here**]({jump_url})"
)

RECRUITING_SHORT = (
    "{hello}{name}<t:{unix}:R> needs **{to_aim} more player{plural}** for a full Pod Draft "
    "{manat} [**Sign up here**]({jump_url})"
)

RECRUITING_READY = (
    "{hello}{name}<t:{unix}:R> has ✅ {yes}{maybe}{tail} {manat} "
    "[**Sign up here**]({jump_url})"
)

RECRUITING_MAYBE = " 🤷 {maybe}"

RECRUITING_SECOND_TABLE = " - join the 2nd table!"

SLOT_FIRE_PING = "{mention} starts <t:{unix}:R>"

ROSTER_REMINDER_TITLE = "🔔 Pod Draft Starting Soon"
ROSTER_REMINDER_LINE = "**{name}** starts <t:{unix}:R>"
ROSTER_REMINDER_MARK = "### 🔔"
ROSTER_REMINDER_HEADLINE = ROSTER_REMINDER_MARK + " **{name}** starts <t:{unix}:R>"

LOBBY_OPEN_HEADLINE = "Lobby opened!"
LOBBY_ARENA_NAME = (
    "Set your **Arena name** (like `YourName#12345`) as your Draftmancer name or use **Join Draft** "
    "below for your personal link."
)
LOBBY_OPEN = (
    "{draftmancer} {headline}\n"
    "**Join the Draftmancer session:** <{url}>\n\n"
    + LOBBY_ARENA_NAME
    + "{mentions}"
)

DRAFT_STARTED = (
    "{hello}{name}started with **{count} {players}** {manat} [**Event Thread**]({thread_url})"
)

RALLY_LOBBY = (
    "{thread_url} needs **{needed} more player{plural}**{waiting} in the {manat} "
    "[**Draftmancer Lobby**]({session_url})"
)

RALLY_LOBBY_WAITING = ", {seated} waiting"

RALLY_QUEUE = (
    "{hello}{name} needs **{needed} more player{plural}** to start, {seated} waiting "
    "{manat} [**Sign up here**]({jump_url})"
)

RALLY_TABLE = (
    "{hello}{name} needs **{needed} more player{plural}** to fire, {seated} waiting "
    "{manat} [**Join here**]({jump_url})"
)

RALLY_NO_POD = (
    "{hello}No pod is gathering right now {manat} [**Today's Launcher**]({launcher_url})\n"
    "Use `/draft` to open one."
)

RALLY_NO_POD_NO_LAUNCHER = "{hello}No pod is gathering right now. Use `/draft` to open one."
