// Discord user ids that can view a closed pod's decklists and draft log before it finishes.
// Gating is visual-only, so this list carries no secret. Set VITE_POD_ORGANIZER_DISCORD_IDS
// (comma-separated) to override the built-in list at build time.

const ENV_IDS = (import.meta.env.VITE_POD_ORGANIZER_DISCORD_IDS ?? "")
  .split(",")
  .map((id) => id.trim())
  .filter(Boolean);

const BUILT_IN_ORGANIZERS: Record<string, string> = {
  Noya: "237762740532412416",
  GatoDelFuego: "178987550780817408",
  ChordOCalls: "507301384979349526",
};

const BUILT_IN_IDS = Object.values(BUILT_IN_ORGANIZERS);

export const POD_ORGANIZER_DISCORD_IDS = ENV_IDS.length > 0 ? ENV_IDS : BUILT_IN_IDS;

export function isPodOrganizer(discordId: string | null | undefined): boolean {
  return !!discordId && POD_ORGANIZER_DISCORD_IDS.includes(discordId);
}
