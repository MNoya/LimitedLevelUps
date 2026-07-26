/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_MODE?: "prod" | "local" | "mock";
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string;
  readonly VITE_POD_ORGANIZER_DISCORD_IDS?: string;
  readonly VITE_P0P1_PREVIEWER_DISCORD_IDS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
