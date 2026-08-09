# Confirm Sign Up and the table plan

## What this covers

What the bot does when more people want to draft than one table seats. Read it when working on the hour before a pod starts: the reminder card, the confirmation ask, lobby opening, or the Ready Check nudge.

It changes nothing when the group is one ordinary table.

## What this is replacing

A human. Noya currently watches any pod thread that gets past ten Yes and steps in by hand to make sure the allocation is the best one available. He is preventing two specific things:

- **A table of 8 firing when 6 and 6 would let everyone play.** Twelve people, eight draft, four go home.
- **A table of 8 firing too fast when two more wanted in.** The room had ten and ran eight.

Both are the same mistake made at the same moment: the pod commits to a shape before anyone checked whether a better shape was available. The bot's job here is to notice that moment and say something useful, not to take the decision away.

## Pillars

These constrain everything below.

**Nobody is ever locked out for not using the system.** A player who clicked Yes yesterday and turns up when pinged at T-10 is fully eligible to draft. Confirmation is how the bot learns things, not how a player earns a seat. Assume the best, then verify.

**Non-engagement is expected and is not a failure.** People will miss the confirmation ask because the UI is unclear, because they are away at T-1h, because they did not understand it, or for no reason at all. Every one of those is valid. A design that only works when people participate does not work.

**The bot suggests, the room decides.** A bot that allocates unilaterally is a bot that a human then has to fight, digging through lobby Settings and slash commands to undo it. Every suggestion the bot makes has to be cheap to ignore. In the end people find their own links and their own tables, and the bot is there to make that easier, not to route them.

**The interface is the feature.** This lives or dies on whether the card is readable at a glance on a phone, whether the buttons say what they do, and whether a player can tell in two seconds what is being asked of them. A correct plan communicated badly is worse than no plan.

## Status — live in production

Decisions taken: confirmation is information and not entitlement, the T-1h Draftmancer session and its early link are cut from v1, a confirmation is persisted on `pod_signal_members.confirmed_at`, Confirm replaces Sign Up on the reminder instead of adding a third button, expected turnout is confirmed players plus unanswered Yes, and the deciding moment uses a held nudge, a second-table button and a confirm-to-start rather than a timed block.

The allocation rule below was rewritten after the 8 Aug Peasant Cube pod, where thirteen players were seated 8 + 5 and the five drafted half an hour after the eight. Thirteen now runs 6 + 7.

One behavioural gap remains: the Ready Check nudge still arms at a fixed eight, so on a 6 + 6 split neither table is nudged and the room starts from the lobby card's own button.

## Valid pods

A table is 6, 8, or 10 players.

- **8 is the pod.** Every suggestion reaches for it first.
- **6 is the fallback.** A real draft, just smaller.
- **10 is a concession.** Used when the alternative is two people not playing, not because bigger is better.

An odd count makes one table of 7 or 9, which is a table carrying one open seat. It settles itself: it finds one more player, or it drops one and plays. Nothing else in the system treats an odd table as a problem to fix.

## What "best allocation" means

Set the odd player aside. Take the combination of table sizes holding the rest that has the **most tables of eight**, breaking ties on the **fewest tables**. Then give the odd player back to the last table that is not already a ten.

That single rule settles every count:

- **12 goes 6 + 6.** No table of 8 fits inside twelve without stranding four.
- **13 goes 6 + 7.** Twelve makes two sixes and the thirteenth joins one of them, which then wants an eighth or drops back to six.
- **14 goes 8 + 6.** One table of eight beats none.
- **16 goes 8 + 8**, not 10 + 6, because two eights beat one.
- **18 goes 8 + 10**, not three sixes, for the same reason: the shape holding an eight wins.
- **30 goes 8 + 8 + 8 + 6**, not three tens.
- **10 stays one table of 10**, because nothing else sums to ten.

**Eleven seats ten and leaves one player waiting.** Six and five would let everybody play, but five is not a table, and a Draftmancer session holds ten seats so there is no eleventh to give. This is the one count where table quality outranks everybody playing, and it is deliberate. The player waiting is the last one to have answered, and a twelfth arriving turns it into 6 + 6.

**Tables come back in the order they can start**: whole tables first, then the odd one, then the waiting seat. Players are dealt into that order confirmed-first, so answering early puts you on a table that fires now and answering last puts you on the one still looking for a player.

That ordering is load-bearing. Seating the certain players first and the uncertain ones last, into tables ordered any other way, guarantees that the table which is already short is also the one built entirely from players who might not come. That is what happened on 8 Aug.

## When the bot starts helping

**At least 8 Yes.** Maybe does not enter the trigger.

A full table's worth of committed players is the point where both failure modes become live. One more person of any kind and somebody is getting left out. One fewer than expected and the table cannot fire at all. Below 8 Yes the pod is either an ordinary table or short, and short is a different problem with its own existing behavior.

Maybe still appears on the card and still matters to the picture, since a pod at 8 Yes and 5 Maybe is a very different evening from 8 Yes and 0. It just does not decide whether the bot speaks up. Yes is the number that means someone actually intends to be there.

## The confirmation ask

At T-1h on a triggered pod, the bot asks the signed-up players to say whether they are coming.

It is asked as a favor to the room, not as a requirement. The honest reason is the good one: the group is close to two tables and the bot needs to know which, so that nobody gets left out at nine o'clock. That is a reason people will act on.

**Not answering costs nothing.** An unanswered Yes is still a Yes and is still counted as someone who is probably coming. The bot plans generously and treats confirmation as evidence that firms up a number, never as a filter that shrinks it.

An explicit "can't make it" is the most valuable answer of all, and the ask should make dropping out as easy as confirming. A clean no is worth more to the plan than three silent maybes.

## Making the picture visible

The reminder card gains a **Confirmed** section above the existing two. Both Yes and Maybe drain into it, and a Maybe who confirms goes straight to Confirmed rather than stopping at Yes.

One meaning per section is the point. Confirmed means answered in the last hour. Yes and Maybe mean answered earlier and not since. Mixing the two makes the only number worth reading impossible to read.

Alongside the counts, the card says what the numbers currently add up to. Thirteen people signed up and nine confirmed is not self-explanatory, but "this looks like two tables" is. When the group is one player short of a better shape, it says so and says which shape, because that is the most actionable message the hour can carry.

Late signups during the window land in Confirmed. Someone signing up twenty minutes before start is confirming by definition. So is someone turning up in the Draftmancer lobby, which stamps the confirmation on arrival for anyone who never pressed the button.

The seat rows under a table carry the difference: ✅ is a seat somebody has answered for, ☑️ is a signup still waiting on its answer. Everywhere else a Yes is a Yes and stays green.

## The deciding moment

Today the Ready Check nudge fires when eight linked players are in the lobby. That is the moment the pod commits, and it is the moment the mistake happens.

On a triggered pod the nudge changes from a prompt to start into a short summary and a choice. It says how many are in the lobby, how many are still expected, what the bot suggests, and offers both starting now and opening a second table. Starting with eight stays one click away, because sometimes eight is right and the other four are not coming.

What it must not do is fire silently or make starting the only visible action.

If the room opens a second table, both tables exist from that moment with their own threads and links, and each fires its own Ready Check when it is a valid pod. Neither waits on the other.

## Flexibility

Any suggested allocation is a suggestion. People can sit at either table, swap between them before the draft starts, ignore the split entirely, or open a table the bot never proposed. The commands to do all of that already exist and stay available.

The bot never moves a player, never removes one from a lobby, and never makes a table that a human then has to dismantle. Anything it opens can be left to expire without consequence.

## Getting the link — deferred

Confirming could hand a player their Draftmancer link there and then, which is a small thank you for answering and a nudge toward showing up. It would be a head start, not a claim: it decides who picks their table first when a pod is busy, never who plays. When the allocation is right nobody misses out, so the head start rarely decides anything, which is the point.

It is out of v1 because the link only exists once the bot owns the Draftmancer session, so handing one out at T-50 means connecting at T-60. That is an hour of held session per busy pod against an unverified question about idle sessions, and it is separable from everything else here.

## Late arrivals

Players who never confirmed are welcome, at every stage, with no exceptions. Someone who shows up after the lobbies open joins whichever table has room. Nobody is moved to accommodate them, no table is reopened, the bot does not rebalance.

Being loose here is a position, not an omission. Rigid rules on a problem this fluid create more edge cases than they prevent, and the room can solve the last few percent by talking to each other.

## A short second table

No plan ever produces a table below six. A table gets there by draining: people drop, or say Yes and never come, and a six becomes a four by nine o'clock. That is normal, not an emergency. It has a thread, a lobby, a link, and a visible count, which is four more things than those players have today. What it needs is to say what it needs, and the existing nudge machinery already knows how to ask. This server usually has people around who are not committed to anything.

The bot does not fold a short table back, does not cancel it, and does not hold table 1 hostage to it.

## Scaling

The preference order generalizes without changing. What does not scale is the coordination. Two threads is a split room for one pod. Four threads is a different event that wants a shared view of all tables at once. This is written for two, occasionally three. A signup reaching four tables is a signal to design that experience properly rather than assume this stretches.

## Surfaces that need copy decisions

Copy is not in this spec, per house rules, but these are the places it has to be right and each is worth its own pass.

- The confirmation ask at T-1h, including how the favor is framed and how visible the drop-out option is.
- The Confirmed section header and how the card summarizes what the counts mean.
- The one-more-player message, which is the highest-leverage line in the whole feature.
- The Ready Check moment, where a start button and an open-second-table button sit next to each other and have to be equally easy to read.
- The second table's opening message and what it asks for when it is short.

## What this touches

Brief, for orientation.

- The reminder card gains a Confirmed section and a confirm action.
- The Ready Check nudge holds while signed-up players are still expected, then posts with a second-table button beside the start button; pressing start with players outstanding costs the presser one ephemeral confirm.
- **Not built:** the nudge still arms at a fixed eight (`_LOBBY_FULL_THRESHOLD`, `bot/services/pod_draft_manager.py`). It needs to arm at the shape being aimed at so a table of 6 nudges at 6, which means deriving full/target/floor from the table's planned size. `spec/pod-lobby-size.md` deferred exactly this when it punted a six-player cap. Until then a 6 + 6 split is started from the lobby card rather than from a nudge, which works but says nothing.
- Second tables already exist. `/pod-table` clones a pod, opens a thread and lobby, and adds the roster. This calls that machinery twice over: once at lobby-open when the answers already show a split, and once from the Ready Check moment when they did not.
- The draft-start second-table offer (`offer_second_table`) stays as the fallback for pods with no roster to ask, such as queue and poll pods.

## Open questions

- **Taking back a seat from a no-show.** Someone who said Yes and never appeared still occupies a seat in the plan, so the tables are built around a player who is not there. Nothing currently removes them, and every count downstream inherits the error. Needs a way for the table to drop them, and a decision about whether that is a person doing it, a timeout, or the lobby noticing they never joined Draftmancer.

- **The per-table Ready Check size.** Still open and the one thing that stops a split pod nudging properly. See the status note above.
- **All copy.** Every string in this feature is a first draft placed to make the logic runnable, not a decision. The one-more-player line matters most.
- **The early link**, deferred with the T-1h session. Whether Draftmancer drops a session that sits empty for most of an hour is still unverified and gates it.
- **Reach.** The T-1h beat already pings the slot role, so this can ride along, but a player with notifications off answers nothing. They are handled when they show up, and the count simply runs low, which the generous-planning rule is designed to absorb.
