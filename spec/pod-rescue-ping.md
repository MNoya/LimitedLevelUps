# Pod rescue ping

**Status: not built.** A preliminary design for one new beat. Read it when picking up cross-format recruiting at the last minute, or when working on the flexible-player model in `pod-nudge-schedule.md` and `pod-launcher-rolling.md`, which this sits beside without depending on.

## What it is

A pod is about to start and is short. At the same time slot, another format collected signups and never reached the floor, so it has no thread and is not going to happen. Those players are the nearest bodies in the server: they wanted to draft at that hour, they said so, and nobody has told them their pod is dead. The rescue ping tells them, once, and points them at the pod that is running.

This is not the flexible-player system. A flexible player signed up for both formats and is already on both rosters. A rescue target signed up for exactly one format and told us they did not want the other. Pinging them is only acceptable because their own pod is definitively over, which is why every condition below is about proving that.

## Trigger

All of these hold, checked at **T-5** for a slot:

1. A pod at that slot is **live**: its lobby is open.
2. That pod is **short**: fewer seated players in Draftmancer than the aim.
3. A sibling format at the same slot **never fired**: no event, no thread, its slot signal still open or expired.
4. That sibling has **at least one signup** who is not already seated in the live pod.
5. The live pod has **not already sent a rescue ping** for this slot.

Condition 3 is the whole ethical basis for the ping and must be read off state, not inferred from a count. Condition 5 needs a claim on the signal, the same shape as `last_call_pinged_at`.

## Why T-5

Earlier is wrong. At T-3h or T-1h the sibling can still fire, and a ping then poaches players out of a pod that would have happened. The question "is the other format dead" is only settled once its slot time has passed without a thread.

T-5 is also the first moment the live pod's shortness is a fact rather than a forecast, because the lobby is open and the bot can count who actually seated themselves rather than who said Yes.

The cost is that five minutes is not much time to see a ping, open Draftmancer and link an Arena handle if the player never has. **Open question:** whether this should run at T-10 on seated count, accepting that the count is still filling and some pings will turn out to have been unnecessary.

## Shape

**Where:** pod chat. The dead format has no thread of its own, and the live pod's thread is the wrong room for people who are not in it yet.

**Who:** the dead format's signups, mentioned individually. Not the slot role, which includes everyone who already declined and everyone already playing. Exclude anyone seated in the live pod.

**What it says,** as content rather than final copy: the format that is not happening, the pod that is, how many seats it has, when it starts, and one link that joins it. Copy goes through the same builders as the rest of the recruiting messages.

**Once.** One ping per live pod per slot, claimed in the database before sending.

## What it must never do

- Ping while the sibling could still fire.
- Ping a player already seated in the live pod.
- Ping when the live pod is at or above its aim.
- Ping twice, including after a restart replays the beat.

## Edge cases to settle when building

- **Three or more formats at a slot,** with two dead siblings. One ping naming the live pod and mentioning everyone from both dead formats, rather than one ping per dead format.
- **Two live pods, both short.** Prefer the one further from its aim, ping once, do not split the rescue targets between them.
- **The live pod fills between the check and the send.** Harmless race, accept it.
- **A pod that fired and was then canceled.** Its players are arguably rescue targets too, but they were told their pod existed and then that it did not, which is a different message. Out of scope for now.

## What it needs that does not exist yet

- A T-5 beat. Current recruiting beats are T-3h, T-2h and T-1h in `pod_underfill.py`.
- Seated-player count read off the live pod's Draftmancer session at ping time, which `PodDraftManager` already tracks but nothing outside the lobby currently reads.
- A per-slot claim column for the rescue ping.
