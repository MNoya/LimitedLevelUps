import { describe, expect, it } from "vitest";

import { isChampionshipSpectator } from "./podDecklistAccess";

const VIEWER_ID = "111";
const OWN_AVATAR = `https://cdn.discordapp.com/avatars/${VIEWER_ID}/hash.png`;
const OTHER_AVATAR = "https://cdn.discordapp.com/avatars/222/hash.png";

describe("isChampionshipSpectator", () => {
  it.each([
    { name: "a logged-out visitor sees no decks", viewer: null, ownRecord: null, sees: false },
    { name: "a logged-in non-player sees every deck", viewer: VIEWER_ID, ownRecord: undefined, sees: true },
    { name: "an undefeated player sees only their own deck", viewer: VIEWER_ID, ownRecord: "2-0", sees: false },
    { name: "a player with a loss sees every deck", viewer: VIEWER_ID, ownRecord: "1-1", sees: true },
  ])("$name", ({ viewer, ownRecord, sees }) => {
    const participants = [{ avatarUrl: OTHER_AVATAR, record: "2-0" }];
    if (ownRecord !== undefined) {
      participants.push({ avatarUrl: OWN_AVATAR, record: ownRecord ?? "0-0" });
    }

    const spectator = isChampionshipSpectator(viewer, participants);

    expect(spectator).toBe(sees);
  });
});
