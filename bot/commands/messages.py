"""Single source of truth for shared user-facing message strings, used across multiple commands and listeners."""

MSG_JOINED_LEADERBOARD = "🎉 Welcome aboard! Run `/help` to see what you can do."
MSG_NOT_REGISTERED = "You're not on the leaderboard. Run `/join` to get started."
MSG_NOT_ON_BOARD = "You're not on the leaderboard."
MSG_NOW_HIDDEN = (
    "🕵️ Your rank is now hidden. [Your profile]({profile_url}) and trophies stay visible. "
    "Run `/join` anytime to show your rank again."
)
MSG_ALREADY_HIDDEN = "Your rank is already hidden. Run `/join` to show it again."
MSG_RANKED_AGAIN = "👋 Your rank is back in the standings."
MSG_TOKEN_INVALIDATED = (
    "⚠️ Your 17lands token appears to be invalid (possibly regenerated). "
    "Please use `/link-17lands` to provide your new token."
)
MSG_ADMIN_ONLY = "This command is reserved for the bot Admin."

MSG_CARD_CREATED_BY = "Created by {name}"

MSG_MOCK_NOT_TEXT_CHANNEL = "Run `/mock-draft` in a server text channel — the thread is created there."
MSG_MOCK_UNKNOWN_SET = "Unknown set `{code}`. Pick one from the suggestions, or use a registered cube format."
MSG_MOCK_NONE_RUNNING = "No mock draft is open right now. Start one with `/mock-draft`."
MSG_MOCK_REPOST_FAILED = "Could not repost the mock draft card. Check that the bot can post in this channel."
MSG_MOCK_COMPLETE = "✅ **{event_name} complete!** [**Draft Recap here**](<{url}>) {manat}"
MSG_MOCK_COMPLETE_CHANNEL = "✅ **{event_name} complete!**"
MSG_MOCK_CLOSED_IDLE = (
    "🕒 **Lobby closed** after {window} of inactivity. Start a new one with `/mock-draft`"
)
MSG_MOCK_CARD_CONTENT = "{role} {state}"
MSG_MOCK_CARD_OPENING = "opening the lobby..."
MSG_MOCK_CARD_OPEN = "looking for drafters"
MSG_MOCK_CARD_NEEDS = "looking for {count} more drafters"
MSG_MOCK_CARD_NEEDS_ONE = "looking for 1 more drafter"
MSG_MOCK_CARD_FULL = "table is full"
MSG_MOCK_CARD_DRAFTING = "drafting now"
MSG_MOCK_CARD_COMPLETE = "draft finished"
MSG_MOCK_CARD_CANCELED = "lobby closed by {actor}"
MSG_MOCK_CARD_CANCELED_NO_ACTOR = "lobby closed"
MSG_MOCK_CARD_CANCELED_IDLE = "lobby closed after {window} of inactivity"
MSG_MOCK_CARD_CLOSES = "Closes after {window} of inactivity"
MSG_MOCK_CARD_DRAFTERS = "✅ In Draftmancer ({count})"
MSG_MOCK_CARD_PLAYERS = "Players ({count})"
MSG_MOCK_CARD_EMPTY_TABLE = "-"
MSG_MOCK_CARD_LOGS_PENDING = "Draft logs saved [**on the site**](<{url}>) {llu}"
MSG_MOCK_CARD_DISCORD_NAME = "Use your Discord name in Draftmancer so the bot can match you"
MSG_MOCK_CARD_RECAP_BUTTON = "Draft Recap"
MSG_MOCK_CARD_SPECTATE_BUTTON = "Spectate"
MSG_MOCK_CARD_THREAD_BUTTON = "Thread"
MSG_LOBBY_FULL_PROMPT = "{count} Players locked in! Initiate Ready Check?"
MSG_LOBBY_FULL_WAITING = "{count} players in the lobby. {outside} more signed up and cannot fit."
MSG_LOBBY_FULL_SPLIT_HINT = "{plan} seats everyone."
MSG_LOBBY_START_ANYWAY = "{outside} players who signed up are not in the lobby. Start without them?"
MSG_LOBBY_START_ANYWAY_BUTTON = "Start Anyway"
MSG_LOBBY_ROOM_MOVED = (
    "This pod moved to a new Draftmancer room. A link you received earlier does not open it. "
    "Press **Join Draft** for your new link."
)

MSG_CONFIRM_NOT_A_POD = "Run `!confirm` inside a pod draft thread."
MSG_CONFIRM_POD_STARTED = "This pod has already opened its lobby."
MSG_CONFIRM_SIGNUP_BUTTON = "Confirm Seat"
MSG_CONFIRM_DONE = "✅ Confirmed for {name}"
MSG_TABLE_SEATED = "You are in Table {numeral}"
MSG_TABLE_FULL_SEATED = "Table {full} is full. You are in Table {numeral}"
MSG_STAGED_POD_SEATS = MSG_TABLE_SEATED + "\n{mentions}"
MSG_POD_BOARD_COLUMN = "{index} Pod of {size}"
MSG_POD_BOARD_SEATED = "✅ {seated} signed up"
MSG_POD_BOARD_OPEN = "⬜ {open} seats open"
MSG_TABLE_COLUMN = "{index} Table of {size}"
MSG_TABLE_COLUMN_ONLY = "Table of {size}"
MSG_TABLE_SEAT_CONFIRMED = "✅ {name}"
MSG_TABLE_SEAT = "☑️ {name}"
MSG_TABLE_EMPTY_SEAT = "⬜ -"
MSG_TABLE_MORE_NAMES = "+{count} more"
MSG_CONFIRM_LOCK_IN = "### Please **{button}** to save your spot"
MSG_CONFIRM_LOCK_IN_TABLE = "### Please **{button}** to save your spot at a Table"
MSG_CONFIRM_SIGNUP_TALLY = " ✅ {yes}"
MSG_CONFIRM_SIGNUP_TALLY_MAYBE = " 🤷 {maybe}"
MSG_SHAPE_TABLE_ONE = "1 table of {size}"
MSG_SHAPE_TABLE_MANY = "{count} tables of {size}"
MSG_SHAPE_TEAM_DRAFT = "a 6p team draft"
MSG_SHAPE_JOIN = " and "
MSG_LOBBY_NUDGE_TITLE = "🔔 Ready to Start"
MSG_BOT_RECONNECTED = "🤖 Bot reconnected — back to managing the lobby."

MSG_JOIN_DRAFT_BUTTON = "Join Draft"
MSG_JOIN_LINE = (
    "### ➡️ Open this [**Draftmancer Link**](<{url}>) to join the draft as {identity}"
)
MSG_LINK_ARENA_PROMPT = (
    "Seats are matched by your MTG Arena handle, like `YourName#12345`\n"
    "Click **Link Arena** below to save it and get your draft link"
)

MSG_DM_RSVP_YES = "✅ You replied **Yes** to {thread}"
MSG_DM_RSVP_MAYBE = "🤷 You replied **Maybe** to {thread}"
MSG_DM_LOBBY_HEADER = "🔔 **Pod Draft Lobby Open**"
MSG_DM_ON_POD = "You are on {pod}"
MSG_DM_TALLY = "👥 **{total} playing** across {pods} pods"
MSG_DM_OTHER_PODS = "↔️ Also running {threads}"
MSG_DM_LOBBY_LINK = (
    MSG_DM_LOBBY_HEADER + "\n\n"
    "{rsvp}\n\n"
    "{join_line}"
)
MSG_DM_LOBBY_LINK_UNLINKED = (
    MSG_DM_LOBBY_HEADER + "\n\n"
    "{rsvp}\n\n"
    + MSG_LINK_ARENA_PROMPT
)
MSG_DM_NOTIFY_HINT = "-# Manage your notifications with `/roles`"
MSG_DM_PREF_ON_TITLE = "🔔 Draft DMs On"
MSG_DM_PREF_ON_BODY = "You'll get your Draftmancer link by DM when a Pod Draft is ready"
MSG_DM_PREF_OFF_TITLE = "🔕 Draft DMs Off"
MSG_DM_PREF_OFF_BODY = "You won't get your Draftmancer link by DM anymore.\nRun `/roles` to manage your notifications."
MSG_DRAFTMANCER_LINK_LEAD = "Draftmancer link will be posted {lead} minutes before."

MSG_POD_WELCOME = (
    "### 👋 Welcome {user} to {pod_drafters}\n\n"
    "Use the buttons below to link your Arena handle, read the Pod Guide and manage Notifications"
)
MSG_MOCK_WELCOME = (
    "{join_line}\n\n"
    "{emoji} You're now on {roles}\n"
    "-# Manage your notifications with the button below"
)
MSG_ARENA_BAD_FORMAT = "❌ Expected a full MTG Arena handle: `ArenaID#12345`"
MSG_ARENA_LINKED = "{emoji} {mention} is **{arena_name}** on Arena"
MSG_ARENA_ALREADY_LINKED_NOTE = "Currently linked as {emoji} **{arena_name}**\nSubmit a new handle to change it"
MSG_ARENA_LINK_CTA = "Please link your Arena handle so the bot knows it's you when joining the lobby"
MSG_POD_ROLE_GRANTED = "{subject} now on {role} and will be notified {ping}"
MSG_POD_NO_MATCH_TO_REPORT = (
    "No pod draft match to report right now. Reporting opens when your round's pairings post."
)
MSG_POD_RESULT_ALREADY_RECORDED = "Round {round_num} recorded. Nothing else to report right now."
MSG_FORMAT_PREFERENCE_BUTTON = "Format Preference"
MSG_DRAFT_STARTS = "Scheduled for <t:{unix}:F> (<t:{unix}:R>)"
MSG_POD_ADDED = "✅ Added to {name}"
MSG_POD_MAYBE = "🤷 Maybe for {name}"
MSG_POD_REMOVED = "❌ Removed from {name}"
MSG_POD_ALREADY_ON = "✅ You are already on {name}"
MSG_POD_ALREADY_ON_HINT = "-# Press ❌ if you need to leave"
MSG_PREFERENCE_LINE = "**Your Preference:** {choice}"
MSG_YOUR_SETS_LINE = "**Your Sets:** {ranking}"
MSG_YOUR_CUBES_LINE = "**Your Cubes:** {cubes}"

MSG_TABLE_NO_SOURCE = "Run `/pod-table` in a pod-draft thread, or pass an `event` to pick the pod."
MSG_TABLE_UNKNOWN_EVENT = "No pod-draft event named `{event}`."
MSG_TABLE_INTRO = "New draft table off this pod."
MSG_LOBBY_GATHERING = "Event thread and Draftmancer lobby will be created once {threshold} players join"
MSG_TABLE_CREATED = "{name} created"
MSG_PLAYERS_JOINED = "Players ({count})"
MSG_TABLE_BUTTON = "Join Table {table}"
MSG_TABLE_SUPERSEDED = "Reopened further down. Join the newer table card."
MSG_TABLE_GOTO = "Go to Table {table}"
MSG_TABLE_LOBBY_STARTER = "{draftmancer_emoji} **{event_name}** created"
MSG_SECOND_TABLE_OFFER = "🔥 The first pod filled up. Click Join to fire a second table."
MSG_POD_RALLY_HINT = "Type `!pod` in another channel to call for more players"

MSG_RESTART_NOT_ORGANIZER = "Only Organizers can restart a draft."
MSG_POD_RESTARTED = "♻️ {actor} restarted the draft"
MSG_POD_RESTARTING = "♻️ **Restarting the draft...**\nSame Draftmancer lobby - no need to rejoin"
