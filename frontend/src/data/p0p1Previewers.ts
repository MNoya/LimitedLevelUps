// Discord user ids that can open a contest's page before its voting window starts, to check a pool
// mid-spoiler. Gating is visual-only, so this list carries no secret: the card fixture ships in the
// bundle either way. Set VITE_P0P1_PREVIEWER_DISCORD_IDS (comma-separated) to override the built-in
// list at build time.

const ENV_IDS = (import.meta.env.VITE_P0P1_PREVIEWER_DISCORD_IDS ?? "")
  .split(",")
  .map((id) => id.trim())
  .filter(Boolean);

const BUILT_IN_PREVIEWERS: Record<string, string> = {
  Noya: "237762740532412416",
  queueknee: "232809189645221888",
};

const BUILT_IN_IDS = Object.values(BUILT_IN_PREVIEWERS);

export const P0P1_PREVIEWER_DISCORD_IDS = ENV_IDS.length > 0 ? ENV_IDS : BUILT_IN_IDS;

export function isP0P1Previewer(discordId: string | null | undefined): boolean {
  return !!discordId && P0P1_PREVIEWER_DISCORD_IDS.includes(discordId);
}
