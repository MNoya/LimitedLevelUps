// Dev-only signed-in identity. The local_supabase_proxy has no auth, so without this
// there is no way to reach an owner-gated surface against the local database.
// Set VITE_DEV_DISCORD_ID in frontend/.env.local; never set it in a deployed build.

import type { AuthUser } from "../auth/AuthContext";

const devDiscordId = import.meta.env.VITE_DEV_DISCORD_ID;

export const DEV_AUTH_USER: AuthUser | null = devDiscordId
  ? {
      id: "00000000-0000-4000-8000-000000000001",
      discordId: devDiscordId,
      username: import.meta.env.VITE_DEV_USERNAME ?? "Local Dev",
      avatarUrl: null,
    }
  : null;
