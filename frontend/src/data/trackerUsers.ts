// Discord user ids that can open the private draft tracker on their own profile.
// Gating is visual-only; the rows themselves are protected by RLS on auth.uid().
// Set VITE_TRACKER_DISCORD_IDS (comma-separated) to override the built-in list at build time.

const ENV_IDS = (import.meta.env.VITE_TRACKER_DISCORD_IDS ?? "")
  .split(",")
  .map((id: string) => id.trim())
  .filter(Boolean);

const BUILT_IN_TRACKERS: Record<string, string> = {
  Noya: "237762740532412416",
};

const BUILT_IN_IDS = Object.values(BUILT_IN_TRACKERS);

export const TRACKER_DISCORD_IDS = ENV_IDS.length > 0 ? ENV_IDS : BUILT_IN_IDS;

export function isTrackerUser(discordId: string | null | undefined): boolean {
  return !!discordId && TRACKER_DISCORD_IDS.includes(discordId);
}
