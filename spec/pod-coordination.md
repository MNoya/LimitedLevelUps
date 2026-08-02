# Playing Pod Drafts

Pod drafts are community Magic Arena drafts we run together every day. You draft with 6 to 8 other players, then play a few rounds against them. Joining is free, nothing is locked in, and your results count on the leaderboard.

This guide describes how pods work right now. It stays current as the system changes.

## When pods happen

The bot posts a Daily Pod Launcher every day in the pod channel. It lists the day's time slots and, under each one, every format that slot is playing:

- Every day: Early Pod at 2 PM ET, Late Pod at 8 PM ET. On Saturday the Late Pod starts at 9 PM ET.

Times are Eastern. Each slot shows its start as a timestamp in your own timezone, so you never have to convert. The community is global, so pick whichever slot fits your day. Mods can also schedule extra pods at other times, which show up as their own signup posts.

Each column moves forward on its own. As soon as a pod finishes, its column shows the result above the next day's slot and starts collecting for that one, so there is always a slot you can join. The other column keeps its own day until its pod plays. A fresh launcher posts every morning at 10 AM ET and carries over everyone who already signed up for that day.

A slot can be held by an event that is already scheduled, the Set Championship being the standing case. That slot takes no signups: the column points at the event instead, with a link to its post and the players who confirmed so far. The pointer shows up on the board the day before as well, so the launcher still says what is happening next even while the slot itself is closed to signups.

The launcher also posts itself again each time a pod finishes, quietly and at the bottom of the channel, so the board is never buried under the pods that already played. Your signups move to it. After the early pod it is the same board again, still carrying tonight's late pod. After the late pod it is the next day's board. The morning post then replaces that one and is the post that pings the queue role.

## How to join

Every pod on the launcher has its own button, named for the time and the format it plays: **Early MSH**, **Early PEASANT**. Click one to add yourself to that pod. A button only ever adds you, so pressing it twice cannot take you back off: the second press just tells you that you are already on that pod. Clicking is a plan, not a promise: if your day changes you can leave, and if you never show up you just catch the next one.

To leave, press **Leave** at the end of the button row. It takes you off every pod on that board, including one that already opened its thread.

You can join more than one pod, including both formats of one time slot, which tells the bot you will play either. If both fill, the bot splits the players who joined both between them so two tables can run instead of one, and it takes only as many as each table needs.

Every click answers you privately with the pod you are on, its start time, and any ping role you just picked up. Sign up for two formats at one time and it names both, and tells you that you play the pod that needs you. The first time you ever join a pod, the channel also gets a public welcome.

When a pod reaches 6 people, it opens for real. The bot posts a signup card with its own thread, and everyone who clicked that pod is carried over as a Yes. The other formats at that time keep collecting behind their own buttons. A pod for a later day waits: it collects signups overnight and opens on the morning of its own day, so nothing starts hours early.

A pod keeps taking signups after it opens, right up to the moment the draft starts. Until then it still shows its full list on the launcher with a link to its thread.

## Saying if you are coming

The signup card has three buttons:

- **Sign Up** — you plan to play.
- **Maybe** — you might play.
- **Can't** — you are out, and you come off the list.

Change your answer any time before the pod starts. Yes and Maybe both put you in the thread, where all the coordination happens.

## Formats

Every pod plays one Magic format, and you know which one before you sign up. A day offers the latest set and often a second format:

- **Latest set** — the current Arena set everyone is drafting.
- **Flashback** — an older set. The launcher names the exact set and pings the Flashback role.
- **Cube** — one of the server's cubes. The launcher names it and links its card list, and pings the Cube role. The signup card carries the same link, so you can read the list before you sign up.

The formats are set ahead of time, so there is no vote and nothing to resolve later. If you want a set or a cube on the schedule, ask a mod.

Run `/pod-schedule` to see a calendar of the formats each day offers over the weeks ahead. It marks today, shows when the next Early and Late pods start in your own time zone, and marks the day a new set arrives, after which every day drafts the new set.

You can also save a **Format Preference** on your welcome card to say what you like to draft. It changes nothing about signing up, it just tells us which formats to schedule more of.

## The lead-up to a pod

In the hour before a pod, a few things happen in the thread:

- The bot posts a reminder that lists the roster. It carries Sign Up and Can't buttons to confirm whether you are still playing. There is no Maybe at this point: you are confirming a yes or a no.
- The pod's status message in pod chat says where it stands: how many players it still needs, and once it has enough, how many said yes and how many said maybe. It is one message from the first signup to the lobby, so the numbers move in place instead of the message coming and going. An hour out it moves to the bottom of the channel, and pings the slot's role if the pod is one or two players short.
- Reaching 8 does not close the pod. Signups stay open, because people do drop before the start, and extra players get a second table.

None of this is binding. It is there so you can see whether the pod is going to fire.

## When a pod fires

About 10 minutes before the start time, the bot opens the draft lobby on Draftmancer and posts the link in the thread. It can also send you the link by direct message. Open the link, set your name, and wait for the draft to begin.

When enough players are ready the bot runs a quick ready check, then starts the draft. A full table of 8 starts as soon as everyone is ready.

## Asking for the last players

A lobby that is one or two players short is the most common way a pod fails to fire. Anyone can type `!pod` in any channel to ask for them. The bot deletes your message and posts one line: which pod is open, how many players it still needs, how many are already sitting in the Draftmancer lobby, and a link to the thread. The line carries a Join Draft button that hands back a Draftmancer link with your Arena name already filled in, so you arrive matched to your leaderboard profile.

Pressing Join Draft also puts you in the pod's thread. So does walking into the Draftmancer lobby on your own, as soon as the bot recognizes your name, so the people drafting and the people talking are the same list either way.

Once a lobby is open the count is read from Draftmancer itself, so it is who is actually there and not who said yes earlier. Before a lobby opens there is nothing to read, so `!pod` reports the signup counts instead and links the signup card. When no pod is gathering at all it points at the day's launcher.

It only ever names one pod, the one closest to a full table, so the message asks you to fill a seat instead of to pick between pods. A pod that already has a full table gets no message: the bot tells you so and posts nothing. Running `!pod` again replaces the previous rally rather than adding a second one, and once the draft starts the rally rewrites itself into a record of the pod firing, so it can never keep asking for players who are no longer needed.

Typed inside a pod's own thread, `!pod` does something else: it moves the lobby card back to the bottom of the thread, for a lobby that conversation has buried. For a mock draft use `!mock` instead: it posts the mock card again at the bottom of the channel, with a Thread button on it, since a reposted card has no thread of its own.

## Table shapes

- **8-player pod** — a full table drafts, then plays 3 rounds. Winners play winners and losers play losers, so nobody is knocked out: everyone plays all three rounds and finishes with a record like 3-0 or 2-1. The two unbeaten players meet in a Trophy Match as soon as they both reach 2-0.
- **6-player team draft** — six players split into two teams of three and draft against each other. This is a different, more social format, so it happens when the group wants it.

On busy nights, once the first table fills, the bot offers a **second table** to the players left over, so more people get to play. A second table plays the same format as the pod it comes from unless a mod picks another.

## After the draft

Report your results in the thread as you play. In an 8-player pod each round also DMs you your pairing with the same dropdown. `/report-results` works anywhere, including in a DM with the bot, and pulls up a private card holding every match you still owe, so a missed DM never stops you from reporting. In a team draft all three of your matches are open from the moment the draft ends, so the card lists all three and you report whichever you played. A match whose players are still finishing an earlier round carries an hourglass and the round it waits on, so the board never reads as ready when only part of a round is. Winning games earns pod points on the leaderboard, so a good run in a pod moves you up the standings the same as a strong ladder result. Pod results are always public: you do not need to opt in, and playing pods is enough to appear on the board.

A reported result can be corrected until a later round reports. In a bracket pod, correcting one re-pairs the rounds after it from the fixed result. Only the players whose record moved get a new opponent: every other pairing stays as it was. The thread gets a single note with the correction, the round that moved, and the new matchups, pinging the players who changed opponent, and their pairing DM is rewritten to the new opponent instead of arriving a second time.

Once the pod finishes, its thread gets a **Play Again** button that signs you up for the same time slot and format on the next day, whenever that format is on the next day's schedule. The launcher also keeps the result: the finished pod stays listed with its winner, whose name links to that pod's page on the website.

Every pod also leaves its final standings in the channel, on the card its thread hangs off. Pods that never gathered signups post a card of their own when they open, so a queue pod and a second table end the night with the same standings card as a scheduled pod.

## Mock drafts

A mock draft is a draft with no rounds after it, for practising a set before it lands. Run `/mock-draft` and the bot opens a Draftmancer lobby right away, with a card in the channel and a thread of its own. Anyone can start one, and any set can be drafted, including one still in spoiler season.

The card shows the link once the bot holds the lobby, then keeps the seat list current as people arrive. Use your Discord name in Draftmancer so the bot can match you. Joining subscribes you to the `Mock Draft` role, so the next one reaches you; switch it off in `/roles` any time and it stays off. It also puts you in `Pod Drafters`, the same as joining any pod does.

Once 8 players are in the lobby, the bot offers a ready check in the thread. Unlike a scheduled pod, a seat it cannot match to a Discord name still counts toward the 8.

When the draft ends, the decks and the draft log are saved to the website. Nothing is paired, nothing is reported, and no pod points are earned.

## Closed decklists

Some pods hide their decklists and draft log on the website until the pod finishes, so nobody can scout an opponent's cards mid-tournament. Standings, pairings, and round results stay visible the whole time. Set Championship pods start closed; a mod can turn Closed Decklist on or off for any pod from the pod Settings panel.

While a pod is closed, sign in with Discord on the website to see your own deck and scroll through your own draft during the rounds. Every decklist opens for everyone once the pod finishes.

## Your first pod, start to finish

1. See the Daily Pod Launcher post and click the pod whose time and format fit your day.
2. Click a second one too if you would play either format.
3. When the pod opens, keep your Sign Up on the card if you still plan to play.
4. About 10 minutes before start, open the Draftmancer link from the thread.
5. Draft, play your rounds, report results, and check the leaderboard.

## For mods

Beyond the daily launcher, you can schedule a pod at any time with the `/draft` command. Pick "Right now" to open a live lobby immediately, or pick a time to post a scheduled signup card. You can preset the set, pairing style, pick timer, and which role gets notified. The signup buttons and thread work the same as a launcher pod.

Which formats a day offers is a table in the bot's code, so ask for a change ahead of time. A pod that already exists can change format from its lobby Settings panel.

Pick Options on the Settings panel holds the two Draftmancer pick controls: seconds per pick, and how many cards each player takes from a pack before passing it. Picks per pack is 1 for a normal draft; set it to 2 for a Pick 2 pod, and the lobby card footer then reads the format as "Pick 2" so everyone sees it. Both are locked once the draft starts.

The pod Settings panel also carries a Closed Decklist toggle: turn it on to hide that pod's decklists on the website until it finishes. Set Championship pods start with it on.

A scheduled pod's Settings panel has a Description button. Whatever you write there takes the place of the "Please RSVP" line on the signup card, so you can say what the pod is about. Leave it empty to bring the RSVP line back. The card drops the note once the draft starts.

Inside a pod thread, the pod controls (ready check, start, team draft, pause, restart, seeding, standings, champion) run the draft. The daily launcher, reminders, and second-table offers all run on their own, so most pods need no hands-on management.
