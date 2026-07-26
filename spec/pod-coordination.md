# Playing Pod Drafts

Pod drafts are community Magic Arena drafts we run together every day. You draft with 6 to 8 other players, then play a few rounds against them. Joining is free, nothing is locked in, and your results count on the leaderboard.

This guide describes how pods work right now. It stays current as the system changes.

## When pods happen

The bot posts a Daily Pod Launcher every day in the pod channel. It lists the day's time slots and, under each one, every format that slot is playing:

- Every day: Early Pod at 2 PM ET, Late Pod at 8 PM ET.

Times are Eastern. Each slot shows its start as a timestamp in your own timezone, so you never have to convert. The community is global, so pick whichever slot fits your day. Mods can also schedule extra pods at other times, which show up as their own signup posts.

Each column moves forward on its own. As soon as a pod finishes, its column shows the result above the next day's slot and starts collecting for that one, so there is always a slot you can join. The other column keeps its own day until its pod plays. A fresh launcher posts every morning at 11 AM ET and carries over everyone who already signed up for that day.

## How to join

Every pod on the launcher has its own button, named for the time and the format it plays: **Early MSH**, **Early PEASANT**. Click one to add yourself to that pod, click it again to leave. That is all it takes. Clicking is a plan, not a promise: if your day changes you can leave, and if you never show up you just catch the next one.

You can join more than one pod, including both formats of one time slot, which tells the bot you will play either. If both fill, the bot splits the players who joined both between them so two tables can run instead of one, and it takes only as many as each table needs.

Every click answers you privately with the pod you are on, its start time, and any ping role you just picked up. Sign up for two formats at one time and it names both, and tells you that you play in the first one to fill. The first time you ever join a pod, the channel also gets a public welcome.

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
- **Cube** — one of the server's cubes. The launcher names it and links its card list, and pings the Cube role.

The formats are set ahead of time, so there is no vote and nothing to resolve later. If you want a set or a cube on the schedule, ask a mod.

You can also save a **Format Preference** on your welcome card to say what you like to draft. It changes nothing about signing up, it just tells us which formats to schedule more of.

## The lead-up to a pod

In the hour before a pod, a few things happen in the thread:

- The bot posts a reminder that lists the roster. It carries Sign Up and Can't buttons to confirm whether you are still playing. There is no Maybe at this point: you are confirming a yes or a no.
- If a pod needs more players, the bot nudges the channel, and closer to start it pings the slot's role.

None of this is binding. It is there so you can see whether the pod is going to fire.

## When a pod fires

About 10 minutes before the start time, the bot opens the draft lobby on Draftmancer and posts the link in the thread. It can also send you the link by direct message. Open the link, set your name, and wait for the draft to begin.

When enough players are ready the bot runs a quick ready check, then starts the draft. A full table of 8 starts as soon as everyone is ready.

## Table shapes

- **8-player pod** — a full table drafts, then plays 3 rounds. Winners play winners and losers play losers, so nobody is knocked out: everyone plays all three rounds and finishes with a record like 3-0 or 2-1. The two unbeaten players meet in a Trophy Match as soon as they both reach 2-0.
- **6-player team draft** — six players split into two teams of three and draft against each other. This is a different, more social format, so it happens when the group wants it.

On busy nights, once the first table fills, the bot offers a **second table** to the players left over, so more people get to play. A second table plays the same format as the pod it comes from unless a mod picks another.

## After the draft

Report your results in the thread as you play. Winning games earns pod points on the leaderboard, so a good run in a pod moves you up the standings the same as a strong ladder result. Pod results are always public: you do not need to opt in, and playing pods is enough to appear on the board.

Once the pod finishes, its thread gets a **Play Again** button that signs you up for the same time slot and format on the next day, whenever that format is on the next day's schedule. The launcher also keeps the result: the finished pod stays listed with its winner, whose name links to that pod's page on the website.

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

The pod Settings panel also carries a Closed Decklist toggle: turn it on to hide that pod's decklists on the website until it finishes. Set Championship pods start with it on.

Inside a pod thread, the pod controls (ready check, start, team draft, pause, restart, seeding, standings, champion) run the draft. The daily launcher, reminders, and second-table offers all run on their own, so most pods need no hands-on management.
