// Discord user ids that may edit public content from the site (transcript text, later pod decks).
// The client gate is cosmetic; the bot re-checks admin on every write. Set VITE_ADMIN_DISCORD_IDS
// (comma-separated) to override the built-in list at build time.

const ENV_IDS = (import.meta.env.VITE_ADMIN_DISCORD_IDS ?? "")
  .split(",")
  .map((id) => id.trim())
  .filter(Boolean);

const BUILT_IN_ADMINS: Record<string, string> = {
  Noya: "237762740532412416",
  ChordOCalls: "507301384979349526",
};

const BUILT_IN_IDS = Object.values(BUILT_IN_ADMINS);

export const ADMIN_DISCORD_IDS = ENV_IDS.length > 0 ? ENV_IDS : BUILT_IN_IDS;

export function isAdmin(discordId: string | null | undefined): boolean {
  return !!discordId && ADMIN_DISCORD_IDS.includes(discordId);
}
