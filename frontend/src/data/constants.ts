// The frontend's single source of truth for values the backend owns elsewhere — keep them in sync when they change.

// Active set fallback when the live set isn't yet known from the network
export const ACTIVE_SET_CODE = "HOB";
export const ACTIVE_SET_NAME = "The Hobbit";

// Site name and the title separator. functions/_middleware.ts imports these too, so the
// browser tab (set by DocumentTitle) and the link-unfurl title render the exact same string.
export const SITE_NAME = "Limited Level-Ups";
export const TITLE_SEPARATOR = " | ";

// LLU community Discord guild
export const DISCORD_GUILD_ID = "775371722065051658";

// Player identity (slug/name/avatar) lives across these views because public_player is
// 17lands-stats-gated; pod-only and self-reported players only appear in the later ones.
// Ordered by priority — first hit wins. Walked by fetchPlayerIdentity and the avatar proxy.
export const IDENTITY_VIEWS = ["public_player", "public_self_reported_events", "public_pod_scoring"] as const;

// 17Lands tier-list ids per set, taken from a tier list's share link
// (https://www.17lands.com/tier_list/<uid>). Add one as each set rotates in.
export const TIER_LIST_UIDS: Record<string, string> = {
  HOB: "528d1c45d1f04b59abac2a897a8928c8",
  MSH: "1c86af8656f7432c83d9f9bb9c92f9df",
  SOS: "e195401b1eaa48e3b5d6670e0ae338e9",
  TMT: "fd5499ae88854ca0ac1bc2ad95ade9b2",
  ECL: "1745e64176864bb2bec132cbd601b604",
  TLA: "efdfa8408fb448be846ac06f9d9192ff",
  SPM: "4f9e6dc9c48c4052805dcfa65568c964",
  EOE: "4f34ccc070464c6c90f85c78972ee6ac",
  FIN: "90be207ac0e34b8ea20ae396c434cbae",
  TDM: "dd9c5b6db6b94ce0bbf3fd285625ceb9",
  DFT: "b0f9dbffd24843d5b8b693f30bc8b1e9",
  FDN: "597d29e75d704ecf9877fc0e4b2c4116",
  DSK: "edec3f514f264753bf4a46a8a2fc7d82",
  BLB: "6057e51272c94a7cb304bd511b7c3bcf",
  MH3: "1775dc0b2fed451cbc5ad4441e2ab9c3",
  WOE: "87b40a05e0974eafa368be44e1d3e0c4",
  MOM: "a7daeb6a90b246e895c8634e34734090",
  VOW: "ac2ca9722737412ba0c4c4c4b2e28598",
  STX: "a2753035da8646038f55b7321de1dfc9",
  PIO: "22b77386e0354d84827e732c226ebc91",
  MKM: "a5c17edddaea4680a28126dae2a5178f",
  LCI: "b8dad7059ff24da28da636a1c50da7e8",
  LTR: "aa685e825b12489a83f081dec8dc308d",
  ONE: "959517c42af04b909ddb6456904b7001",
  BRO: "b8d4ba9d1bad49828bfa6371f6b4f09b",
  DMU: "e12ee0b1fadc4ab7b8de4c3730878a90",
  HBG: "d24c2d28b6aa4146912b2ca92c503fe1",
  SNC: "8513f3fa48f140c0a4792862f530dea9",
  NEO: "0b2b04f23e104ddba3501cd009385d60",
  MID: "ef928c7c17bb4f57b09a75be5daf7df9",
  AFR: "1d901171375f4cff9834c751667c4254",
  IKO: "db593297907e41af93eedd994e26da28",
  ELD: "30588ade239246d0ab12393d00dc801a",
  KTK: "a6346d2850ef45918508db61d057388e",
};

// Per-set host graders. With a consensus list their grades join onto it by card name and
// show in the popup; with no consensus list the first grader drives grid placement and the
// popup compares all graders side by side.
export const TIER_LIST_GRADERS: Record<
  string,
  Array<{ name: string; uid: string }>
> = {
  MSH: [
    { name: "Alex", uid: "b07c077b8c8145288f75d71bf4f90d65" },
    { name: "Marc", uid: "e0c4c50e90914ac390a1f792e0717ed2" },
  ],
  SOS: [
    { name: "Alex", uid: "3dda4b67b4b0403caeb0a744887b0208" },
    { name: "Marc", uid: "09ccc33bf4d6461f9c73de01bd8efe0c" },
  ],
  TMT: [
    { name: "Alex", uid: "c1489602e3d544d9aa90718692f16a32" },
    { name: "Marc", uid: "a8a502ee50d84a31b6a501bb6b4d5920" },
  ],
  ECL: [
    { name: "Alex", uid: "4f09f4891cc148f0bb7afe510d4605ec" },
    { name: "Marc", uid: "0fef073a7db5401ba7e260e8649f2bea" },
  ],
  TLA: [
    { name: "Alex", uid: "6554520225504ef9a3d5360c062a8274" },
    { name: "Marc", uid: "10ab962ac03b4774b7cd2cb8bec152af" },
  ],
  SPM: [
    { name: "Alex", uid: "78638999335b4900b961503d6f58c4a9" },
    { name: "Marc", uid: "796eb012eb3b4081929da9679ea577d0" },
  ],
  EOE: [
    { name: "Alex", uid: "13384ec719b74936b0c700126469a22a" },
    { name: "Marc", uid: "969006b0242e4ab4bfd9b85e3fe4c73e" },
  ],
  FIN: [
    { name: "Alex", uid: "9f907d1c51834c4696383aa30f65523a" },
    { name: "Marc", uid: "35157ab6c45a48a2aabc92853e389af3" },
  ],
  TDM: [
    { name: "Alex", uid: "b13d129e71b8467dab4de66f770c6b10" },
    { name: "Marc", uid: "bb8970942c3d4e42bd0fe91528befada" },
  ],
  OTJ: [
    { name: "Alex", uid: "df75c79fba154f21b4a8bf751b8aa0a4" },
    { name: "Marc", uid: "317fe1336cac48c8b3a2d731a844ccbe" },
  ],
};

// Name/date for tier-list sets absent from the live feed; future startDate shows a PREVIEW badge
export const TIER_LIST_PREVIEW_SETS: Record<
  string,
  { name: string; startDate: string }
> = {
  HOB: { name: "The Hobbit", startDate: "2026-08-11" },
  MSH: { name: "Marvel Super Heroes", startDate: "2026-06-23" },
  MH3: { name: "Modern Horizons 3", startDate: "2024-06-11" },
  MOM: { name: "March of the Machine", startDate: "2023-04-18" },
  VOW: { name: "Innistrad: Crimson Vow", startDate: "2021-11-11" },
};

// Same-origin proxy to 17Lands' dict-shaped tier-list endpoint (ratings +
// last_updated), which has no CORS headers for direct browser use. Served by
// functions/api/tier-list in prod and a vite proxy entry in dev.
export const TIER_LIST_DATA_BASE = "/api/tier-list";

// Per-uid full fetch URLs for tier lists not served by 17Lands (e.g. a fixture
// snapshot under public/tier-fixtures for a set not yet public upstream).
export const TIER_LIST_DATA_BASE_OVERRIDES: Record<string, string> = {};
