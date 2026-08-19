# Pod Table Organizer

## The job

In the last ten minutes before a pod, someone has to decide what the table is going to play. Today that someone is a human: they read how many people said yes, count who is actually sitting in the Draftmancer lobby, notice that two of the yes players never showed, decide whether the room is still growing or has stopped, and then tell the table what its options are. A pod that ends up at four can still draft, but only as Pick 2, and most players do not know that is on the table until someone says so.

The bot has every number that decision needs and uses none of them. This is the layer that reads them and puts the choice in front of the table.

## What it watches

One tick per pod, every minute, from the lobby opening at T-10 until the draft starts. Each tick takes one snapshot:

- **In Draftmancer**: players the bot has matched to a seat in the Draftmancer session. This is the only thing the cards ever call being in the pod, and no roster number is allowed to borrow the phrase.
- **Ceiling**: confirmed plus yes plus maybe, every player who could still walk in. A pod whose lobby already holds more than its roster (walk-ins from `!pod`) takes the larger number.
- **Waiting on**: confirmed and yes players who are not in the lobby yet. A maybe is never a player the room waits on.
- **Settled for**: minutes since the lobby count last moved.

The tick stops when the draft starts, and stays quiet while a ready check is running. A check is the table already answering the question.

## When it speaks

Never offer a smaller pod while a bigger one is still plausible. There are two ways the bot learns that nobody else is coming, and they carry different timing:

- **From the roster, at once.** A ceiling of exactly 4 means the shape is settled before the lobby even opens, so the options go up as soon as two of those four are in Draftmancer. Four signups and two players in the room at T-9 is not a situation that improves by waiting.
- **From the clock, by waiting.** Every other pod holds until its start time has passed and the lobby has sat still for 2 minutes.

Players who said yes and never arrived do not hold the room past its start time. They were named once at T-5, which is the room's one obligation to them, and a pod cannot wait on an answer nobody is giving.

## What it offers

Read against the players in the lobby, once the pod is past the point of waiting:

| In Draftmancer | The choice put to the table |
|---|---|
| 8 or more | Nothing to decide. Prompt the ready check. |
| 7 | Nothing to decide. Prompt the ready check. |
| 6 | Team Draft, or start as a normal six. |
| 5 | Nothing. Five is odd, so there is no shape to offer and no check worth starting, and there is nothing to say that a player in the room cannot already see. |
| 4 | Pick 2 Round Robin, or keep waiting. On the sets that play it. |
| 3 or fewer | No pod to shape. Points at `!pod`, and otherwise leaves the room alone. |

Six is where the room is asked proactively for the first time. Team Draft today is only ever offered to whoever presses Start Ready Check with exactly six in the lobby, so a table of six that never presses anything is never asked.

## It offers, the table chooses

An offer is sized when it is posted and is not tied to the lobby after that, so players arriving do not disturb it. A room that grows past an offer is left alone on purpose: it is rare, and every rule written for it costs more than it saves.

Nothing on this path changes a pod's settings on its own, including at four where Pick 2 is the only playable shape. An organizer suggests and the table decides, and a format switching itself under a player who did not ask for it is worse than a pod that does not fire. Every outcome stays changeable in Settings afterwards, as it is today.

## Every message is sent once

The organizer owns one card in the pod's thread. It carries the same three things at every stage, so a player learns to read one surface: who is in, who the room is waiting on, and what happens next. Only the buttons that apply right now are on it.

That card is edited in place for the life of the pod. It is never reposted, never duplicated, and never posted a second time because the situation changed. A pod that ends at three players ends quietly.

The players who said yes and are not in the lobby are named once, at T-5. Five minutes out is early enough that they can still walk in and early enough that the players already sitting there have not given up, which is the whole point of naming them. The roster was pinged when the lobby opened at T-10, so this is the second and last thing either of them hears from the bot.

Editing in place means conversation can push the card up the thread, so `!pod` inside the thread moves the offer card to the bottom the way it already moves the lobby card. A player asking for the card is not the bot repeating itself, which is what keeps this inside the rule.

## The ready check keeps its own ask

Whoever presses Start Ready Check gets asked the question that fits the count in front of them: six is asked about Team Draft, which is what happens today, and four is asked about Pick 2, which does not exist yet. The organizer is the proactive path and the check is the safety net, and both ask the same question about the same room.

## What this is built from

Already built: the Pick 2 Round Robin vote card, the Team Draft vote card, the shared tally rendering under both, the lobby-full ready check prompt, the `!pod` rally, and the roster reads behind the confirmation card. Both vote cards keep the buttons and the wording they ship with, Wait included, so a player who has seen one of them before reads the new moments without learning anything.

New: the per-pod tick, the snapshot, the ladder above, and one card that owns every offer so two of them can never sit in one thread disagreeing.

## Prerequisite

A pod at four or five signups never opens a thread today, since a launcher slot graduates at six. There is no lobby for any of this to happen in. A pick-2 set opens its thread at four inside the last hour before the start, which is what gives a thin pod a room to be organized in at all.
