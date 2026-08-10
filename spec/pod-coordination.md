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

To leave, press **Leave** at the end of the button row. It takes you off every pod on that board, including one that already opened its thread. Leaving by mistake costs nothing: sign up again and you are back where your first signup put you, ahead of everyone who joined after it. In the hour before a pod starts, its roster card also lists who has left, so the room can see who it is no longer waiting for.

You can join more than one pod, including both formats of one time slot, which tells the room you will play either. The launcher marks you with ◈ on every pod you are on and lists you last on each of their rosters, so everyone can see which bodies two tables are both counting on. Nothing takes you off one pod because another one opened. If both fill, you are in both threads and you pick the one that needs you.

Every click answers you privately with the pod you are on, its start time, and any ping role you just picked up. Sign up for two formats at one time and it names both, and tells you to play the pod that needs you to fill a table if both are created. The first time you ever join a pod, the channel also gets a public welcome.

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

- The bot posts a reminder that shows the roster as the tables it makes. It carries Confirm and Leave buttons to say whether you are still playing. There is no Maybe at this point: you are confirming a yes or a no.
- The pod's status message in pod chat says where it stands: how many players it still needs, and once it has enough, how many said yes and how many said maybe. It is one message from the first signup to the lobby, so the numbers move in place instead of the message coming and going. An hour out it moves to the bottom of the channel, and pings the slot's role if the pod is one or two players short.
- Reaching 8 does not close the pod. Signups stay open, because people do drop before the start, and extra players get a table of their own when the pod splits.

None of this is binding. It is there so you can see whether the pod is going to fire.

## When a pod fires

About 10 minutes before the start time, the bot opens the draft lobby on Draftmancer and posts the link in the thread. It can also send you the link by direct message. Open the link, set your name, and wait for the draft to begin.

When enough players are in the lobby, anyone can start a ready check from the lobby card in the thread. The bot posts a card of its own carrying I'm Ready, Not Ready and Stop, and the Draftmancer prompt pops up at the same time. Answer on whichever is in front of you, it counts either way. The card shows who has answered and who has not, and the draft starts by itself the moment the last seat says I'm Ready. A full table of 8 starts as soon as everyone is ready.

When the draft starts, the pod's status message in pod chat is replaced by a line at the bottom of the channel saying the pod fired, how many players are in it, and linking the thread. It posts quietly, with no ping and no notification, so the channel reads that the draft is under way without calling anyone away from the table.

Not Ready is how you say wait for me: it marks your seat on the card and holds the start, and you can press I'm Ready once you are set. Stop calls the whole check off and is open to everyone, not only the organizer. The pinned lobby card keeps Force Start, which drafts without the players who never answered, behind a confirmation naming who gets left behind.

A check runs for the table it was started on, so a pod never drafts with a table nobody checked. If someone joins or drops out while it is running, the check pauses instead of starting.

A player the bot knows walking in mid-check joins it already ready, and the pause clears on its own. Turning up is the answer. A seat the bot cannot place keeps the check paused until they press I'm Ready for themselves, which brings them in the same way. A player who dropped out sets it going again by coming back, and the paused card carries a Draftmancer link so they have the way in. Resume Ready Check is there for the rest: it runs the check again for the lobby as it stands.

Your answer sticks for as long as you are in the Draftmancer lobby. Say you are ready once and you stay ready, through a check somebody stops, through one that runs out of time, and through the next one. Leave the lobby and your answer goes with you.

## Asking for the last players

A lobby that is one or two players short is the most common way a pod fails to fire. Anyone can write `!pod` in any channel to ask for them. Start the message with it and the rest is yours to write, so `!pod anyone free tonight` works. Write a set or cube code as the first word and it asks for that format, so `!pod DOM for the boomer magic enjoyers` calls for the DOM pod even when another one is closer to firing. A format nobody is drafting right now gets you the normal answer, so you still learn which pod is live. Your message stays up and the bot posts one line under it: which pod is open, how many players it still needs, how many are already sitting in the Draftmancer lobby, and a link to the thread. The line carries a Join Draft button that hands back a Draftmancer link with your Arena name already filled in, so you arrive matched to your leaderboard profile. The lobby card lists `!pod` in its Commands block, so the pod that needs players names the way to ask for them.

Pressing Join Draft also puts you in the pod's thread. So does walking into the Draftmancer lobby on your own, as soon as the bot recognizes your name, so the people drafting and the people talking are the same list either way.

Once a lobby is open the count is read from Draftmancer itself, so it is who is actually there and not who said yes earlier. Before a lobby opens there is nothing to read, so `!pod` reports the signup counts instead and links the signup card. A second table that is still collecting players on its Join card is read off that card, and `!pod` links you straight to it. When no pod is gathering at all it points at the day's launcher.

It only ever names one pod, so the message asks you to fill a seat instead of to pick between pods. It picks the one you can still join: an open lobby with seats left first, then a second table collecting players, then a pod gathering for later. Between two pods starting at the same time, which is what a day offering two formats in one slot looks like, it names the one closest to firing, and a pod that already has a full table comes after one still short, since a pod nobody needs to fill would hide the pod that needs players. A pod that is already full or already drafting comes last, so it never hides the table its leftovers are trying to fire. When a full table really is the only thing happening, the bot tells you so and posts nothing. A second `!pod` replaces the rally the channel already has, so a channel never holds two of them reading different numbers. Once the draft starts the rally is deleted, so it can never keep asking for players who are no longer needed, and pod chat carries the record of the pod firing.

Written inside a pod's own thread, `!pod` does something else: it moves the lobby card back to the bottom of the thread, for a lobby that conversation has buried. A pod with no card up, because it is already drafting or already done, has nothing to move, so there you get the normal rally. Naming a format gets you the rally too: someone asking for a set is asking about a pod, not about the card in front of them. A mock draft's thread works the same way. Its card in the channel is a separate one, and `!mock` is what moves that: the card posts again at the bottom of the channel, with a Thread button on it, since a reposted card has no thread of its own.

## Table shapes

- **8-player pod** — a full table drafts, then plays 3 rounds. Winners play winners and losers play losers, so nobody is knocked out: everyone plays all three rounds and finishes with a record like 3-0 or 2-1. The two unbeaten players meet in a Trophy Match as soon as they both reach 2-0.
- **10-player pod** — the same 3 rounds, and pairings still go up as soon as two players reach the same record. Ten does not split evenly, so one match per round puts a player against someone on a different record. Those show under a Pair Up heading, so an uneven match always reads as one. Round 3 can open with three unbeaten players, which makes two Trophy Matches, and two players can finish 3-0.
- **6-player team draft** — six players split into two teams of three and draft against each other. Six players is what this format is for, so it is what six players get, and there is nothing to vote on. A pod whose roster comes to six opens as a Team Draft, a table of six built by a split does too, and a lobby that reaches its ready check with six players in it is moved to one there. A note in the thread says the pairings moved. If the pod turns out to be another size, because two more sign up or two more walk into the Draftmancer lobby, the pairings move back on their own. Six players who want to play something else set Pairings in Settings: that is the way out, and from then on the pod keeps what you picked.
- **4-player round robin** — four players draft and each one plays the other three, one per round. Everyone still finishes with a record like 3-0 or 2-1, worth the same pod points as any other pod.

On busy nights a pod splits into tables before it opens, not after. A Draftmancer room holds ten, so a pod expecting more than ten waits at its ten minute mark instead of opening one. The roster card moves to the bottom of the thread with everyone mentioned above it, asking for confirmations, and no draft link is posted yet. That wait is the whole point: which tables the pod should run depends on who is actually coming, and opening a room first decides it before anyone knows.

At the start time the bot builds the tables the confirmed players ask for, opens one for each, and posts a list of them in the thread. Every table plays the format the pod was signed up for.

Each table opens its Draftmancer room at the size it was planned for, so a table of ten holds ten and a table of six holds six, and it offers a ready check as soon as everyone it is expecting has arrived. A table waiting on one more player is waiting on somebody real. If a late player turns up after the tables are built, send them to the last table and widen it from Max Players on that table's Settings panel.

Each table's card carries only the players on it. There are no signup buttons and no start time on it: the draft is beginning, so there is nothing left to answer.

Organizers have two controls on the roster card while it is asking for confirmations. 📋 opens a private list with **Confirmed Players** and **Declined Players**, for recording what somebody said in chat but never pressed, and 🚀 **Open Tables** ends the wait early and deals the tables there and then. Both edits are posted in the thread naming who made them and who they were about, since the room is waiting on those answers. After the split, 📋 **Move Players** sits under the list of tables and moves people between them.

You do not have to go looking for your table. The players a new table is for are named in that table's own thread, and the list in the main thread links to every table. On a pod that split, the lobby post carries no draft link, only the **Join Draft** button, which sends you to the table with a seat for you even when you press it in the wrong thread.

A table that opens short of six asks pod chat for the players it needs, once. Anyone can open one more table at any time with `/pod-table`.

When a lobby sits at 4 players for a couple of minutes with nobody new arriving, and the pod's start time has already passed, the bot asks that lobby whether to play now as a Pick 2 Round Robin or keep waiting. It only asks on the sets being tried out for it, HOB and MSH to start with, and it never asks before the start time, since more players are still expected until then. All 4 have to agree, so Wait is not a verdict: the card stays open, you can change your vote, and someone who wanted to wait can move to Round Robin once it is clear nobody else is coming. The card also reminds you that `!pod` in another channel calls for more players. Once all 4 agree the pod switches to 2 picks per pack and round robin pairings, both still changeable in Settings. A ready check on a round robin pod does not warn about the short roster, since 4 is the point.

## After the draft

The moment the draft ends, before the first pairings go up, the bot posts a link to the pod voice channel. The card under it shows who is already in there. Voice is optional and listening is fine.

Report your results in the thread as you play. In an 8-player or 10-player pod each round also DMs you your pairing with the same dropdown. `/report-results` works anywhere, including in a DM with the bot, and pulls up a private card holding every match you still owe, so a missed DM never stops you from reporting. In a team draft all three of your matches are open from the moment the draft ends, so the card lists all three and you report whichever you played. A match whose players are still finishing an earlier round carries an hourglass and the round it waits on, so the board never reads as ready when only part of a round is. Winning games earns pod points on the leaderboard, so a good run in a pod moves you up the standings the same as a strong ladder result. Pod results are always public: you do not need to opt in, and playing pods is enough to appear on the board.

Share your deck in the last round. Post a screenshot of it in the thread, and submit your deck colors with the Submit Deck button or with `/report-results`. While the last tables are still playing, the bot posts one plain reminder in the thread if anyone who finished has not posted a screenshot yet, with nobody pinged. Five minutes after the last result of the pod, it mentions the players who still owe a screenshot or their colors. The pod result posts in the channel once the top finishers have both, and ten minutes after the last result at the latest.

A reported result can be corrected until a later round reports. In a bracket pod, correcting one re-pairs the rounds after it from the fixed result. Only the players whose record moved get a new opponent: every other pairing stays as it was. The thread gets a single note with the correction, the round that moved, and the new matchups, pinging the players who changed opponent, and their pairing DM is rewritten to the new opponent instead of arriving a second time.

Once the pod finishes, its thread gets a **Play Again** button that signs you up for the same time slot and format on the next day, whenever that format is on the next day's schedule. The launcher also keeps the result: the finished pod stays listed with its winner, whose name links to that pod's page on the website.

Every pod also leaves its final standings in the channel, on the card its thread hangs off. Pods that never gathered signups post a card of their own when they open, so a queue pod and a second table end the night with the same standings card as a scheduled pod.

## Mock drafts

A mock draft is a draft with no rounds after it, for practising a set before it lands. Run `/mock-draft` and the bot opens a Draftmancer lobby right away, with a card in the channel and a thread of its own. Anyone can start one, and any set can be drafted, including one still in spoiler season.

The card shows the link once the bot holds the lobby, then keeps the seat list current as people arrive. Use your Discord name in Draftmancer so the bot can match you. Joining subscribes you to the `Mock Draft` role, so the next one reaches you; switch it off in `/roles` any time and it stays off. It also puts you in `Pod Drafters`, the same as joining any pod does.

Once 8 players are in the lobby, the bot offers a ready check in the thread. Unlike a scheduled pod, a seat it cannot match to a Discord name still counts toward the 8.

When the draft ends, the decks and the draft log are saved to the website. Nothing is paired, nothing is reported, and no pod points are earned.

A lobby nobody joins does not sit there. Anyone can close a mock draft from the pod Settings panel, and the bot closes one on its own after an hour with nobody entering or leaving the Draftmancer lobby. The card in the channel says which of the two closed it, and a lobby that timed out says so in its thread and archives it. Start a new one with `/mock-draft` whenever you want.

A draft under way is never closed by the timer, and once the draft ends the button is gone: the decks and the draft log on the website stay put.

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

Beyond the daily launcher, you can schedule a pod at any time with the `/draft` command. Pick "Right now" to open a live lobby immediately, or pick a time to post a scheduled signup card. You can preset the set, pairing style, and pick timer. The signup buttons and thread work the same as a launcher pod.

Notify starts off, so the pod pings nobody until you turn it on. Anyone can run `/draft`, and a pod that nobody asked for should not wake a role at a bad hour. A quiet pod still reaches the channel on its own once it is short of players. Either way the bot posts one line where you ran the command, naming the pod and linking its card, and a scheduled card carries your name in its footer so players can see who organized it.

Which formats a day offers is a table in the bot's code, so ask for a change ahead of time. A pod that already exists can change format from its lobby Settings panel.

Draft Setup on the Settings panel holds the shape of the draft: the seconds each player gets per pick, and how many packs each player opens. On a cube pod it also takes how many cards a pack holds, which a set pod does not offer, since a set draft opens the set's own packs. Leave a field empty to keep what the pod already runs. Next to it, Mode toggles between Pick One and Pick Two, which is how many cards a player takes from a pack before passing it. Pick One is the normal draft and the button sits grey; turn it on for a Pick Two pod and it goes green, and the lobby card footer reads the format as "Pick 2" so everyone sees it. All of them are locked once the draft starts.

Draft Setup, Mode, and Max Players are on the panel from the moment the pod exists, so a scheduled pod can be set up days before anyone opens its lobby. The pod keeps what you pick and the Draftmancer session takes it when the lobby starts.

Max Players sets the table size: 6, 8, or 10 seats. A six-seat table is a 3v3 team draft, so the bot moves the pairings there on its own, and it asks that lobby to start as soon as six players are in it. A cap below the players already in the Draftmancer lobby is refused, so shrinking a table that filled up means removing someone first with Kick Player.

If someone loses their connection mid-draft, the draft stops on Draftmancer until they come back. The bot posts a card naming who went and counting down to the vote that opens if they stay gone. A player who comes back inside those two minutes is never asked about: the card flips to "Everyone is back" and the draft carries on.

If the two minutes run out, the waiting card gives way to the vote and the table picks how to continue, the same way the Team Draft offer works. Replace With Bot keeps every pick made so far and gives the empty seat to a Draftmancer bot. Restart Draft throws away every pick and reopens the lobby on the same link. A majority of the players still at the table decides, the two columns show who picked what, and the vote card keeps that tally once it is settled. Under it the lobby card is reposted, listing who is in Draftmancer and carrying the usual Ready Check, Settings, and Force Start, so the table starts again from the card it already knows.

Restart Draft also sits on the Settings panel for as long as the draft is running, for a pod that started with the wrong settings or went wrong some other way. It appears when the picks start and goes away when they finish. It stops the draft, throws away every pick, and reopens the lobby on the same Draftmancer session, so nobody has to rejoin. A full even table goes straight into a fresh ready check; any other roster gets the lobby card reposted and starts the check from its button. Only Organizers can use it, and it asks to confirm first.

The pod Settings panel also carries a Closed Decklist toggle: turn it on to hide that pod's decklists on the website until it finishes. Set Championship pods start with it on.

A scheduled pod's Settings panel has a Description button. Whatever you write there takes the place of the "Please RSVP" line on the signup card, so you can say what the pod is about. Leave it empty to bring the RSVP line back. The card drops the note once the draft starts.

The Settings button stays on the lobby card after the draft finishes, because the panel is where you fix things during the rounds. Once a pod has pairings the panel carries Manage Rounds: pick a round and you get the same editor the 🔧 on a round message opens, where you can reassign a match's two players or set a result. Only Organizers can use it. Each round message keeps its own 🔧 where there is room for it, but a ten-player round fills every dropdown slot, so on those pods the Settings panel is the way in.

Inside a pod thread, the pod controls (ready check, start, team draft, pause, restart, seeding, standings, champion) run the draft. The daily launcher, reminders, and second-table offers all run on their own, so most pods need no hands-on management.
