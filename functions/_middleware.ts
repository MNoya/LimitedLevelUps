// Serves the SPA index.html for every HTML route and rewrites its <head> meta per
// route so link unfurls (Discord, Twitter, Slack) reflect the page instead of the
// single baked-in preview. Crawlers don't run JS, so this is the only place per-page
// titles, descriptions, and thumbnails can land.
//
// Embed title and browser tab title diverge on purpose. The embed carries the brand in
// the gray og:site_name line, so og:title is the bare label (e.g. "MSH Leaderboard",
// "Noya · Player Profile"). The tab has no gray line, so <title> appends the brand:
// "MSH Leaderboard | Limited Level-Ups". Home is the exception: no gray line, the brand
// is the title. DocumentTitle reproduces the tab title client-side on SPA navigation.
//
// Thumbnail per route: a player's Discord avatar (falling back to the baked LLU logo
// when they have none), a set's white symbol on set routes, the LLU logo everywhere else.

import {
  PUBLIC_SUPABASE_URL,
  PUBLIC_SUPABASE_PUBLISHABLE_KEY,
} from "../frontend/src/data/public-supabase-config";
import { SITE_NAME as SITE, TITLE_SEPARATOR, TIER_LIST_PREVIEW_SETS } from "../frontend/src/data/constants";
import { mtgoSetName } from "../frontend/src/data/mtgoSets";
import { resolveContestByCode, resolveFeaturedContest } from "../frontend/src/data/p0p1Slots";
import { categoryFromSlug, episodeSlugBase } from "../frontend/src/data/episodes";
import { cubeVariantForBoard } from "../frontend/src/data/cubeVariants";
import { skeletonsFor } from "../frontend/src/data/skeletons";

const EPISODE_CATEGORY_DESCRIPTIONS: Record<string, string> = {
  "Set Review": "Card-by-card set reviews and first impressions for MTG limited",
  Draft: "Draft playthroughs, archetype guides and deckbuilding for MTG limited",
  Sealed: "Sealed and prerelease deckbuilding and gameplay",
  Rankings: "Tier lists, top-10s and best-of-year rankings",
  Metagame: "Format state, metagame updates and tournament reports",
  Coaching: "Coaching sessions and gameplay reviews",
  Guest: "Interviews and conversations with limited players",
  Evergreen: "Timeless limited skills, fundamentals and strategy",
};

const EPISODE_WATCH_FALLBACK = "Watch this episode";
const EPISODE_LISTEN_FALLBACK = "Listen to this episode";

const LEADERBOARD_DESCRIPTION =
  "Check ranks and trophies from the community. /join on Discord to share your drafts and climb the leaderboard";
const HOME_DESCRIPTION = "Weekly episodes, set reviews, strategy and community events. Join the Discord and climb the leaderboard.";

const P0P1_PICK_SENTENCE = "Pick a team of eight cards you think will perform best from the upcoming set.";

// A bare /p0p1 unfurls whichever contest is featured; /p0p1/<code> unfurls that one, so an archive
// link carries its own set symbol instead of the live contest's.
const p0p1Meta = (routeCode: string | undefined): RouteMeta => {
  const now = Date.now();
  const contest = routeCode ? resolveContestByCode(routeCode, now) : resolveFeaturedContest(now);
  if (contest === null) return page("P0P1 Challenge", P0P1_PICK_SENTENCE);

  let description = P0P1_PICK_SENTENCE;
  if (now > contest.votingDeadline.getTime()) {
    description = now < contest.scoringDate.getTime()
      ? `${P0P1_PICK_SENTENCE} Preliminary data now available!`
      : `${P0P1_PICK_SENTENCE} Final standings now available!`;
  }
  return page("P0P1 Challenge", description, { kind: "setSymbol", code: contest.code });
};

type ImageIntent =
  | { kind: "url"; url: string }
  | { kind: "setSymbol"; code: string }
  | { kind: "avatarProxy"; slug: string }
  | null;

type RouteMeta = {
  ogTitle: string;
  tabTitle: string;
  siteName: string | null;
  description: string | null;
  image: ImageIntent;
};

const page = (label: string, description: string | null, image: ImageIntent = null): RouteMeta => ({
  ogTitle: label,
  tabTitle: `${label}${TITLE_SEPARATOR}${SITE}`,
  siteName: SITE,
  description,
  image,
});

const HOME_META: RouteMeta = { ogTitle: SITE, tabTitle: SITE, siteName: null, description: HOME_DESCRIPTION, image: null };

const slugToName = (slug: string): string => slug.replace(/-/g, " ");

const titleCaseSlug = (slug: string, setCodes: Set<string>): string =>
  slug
    .split("-")
    .map((word) => {
      const upper = word.toUpperCase();
      if (setCodes.has(upper)) return upper;
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");

const restGet = (query: string): Promise<Response> =>
  fetch(`${PUBLIC_SUPABASE_URL}/rest/v1/${query}`, {
    headers: {
      apikey: PUBLIC_SUPABASE_PUBLISHABLE_KEY,
      authorization: `Bearer ${PUBLIC_SUPABASE_PUBLISHABLE_KEY}`,
    },
    cf: { cacheTtl: 600, cacheEverything: true },
  });

const fetchSetCodes = async (): Promise<Set<string>> => {
  try {
    const resp = await restGet("public_sets?select=code");
    if (!resp.ok) return new Set();
    const rows = (await resp.json()) as Array<{ code: string }>;
    return new Set(rows.map((r) => r.code.toUpperCase()));
  } catch {
    return new Set();
  }
};

const fetchSetName = async (code: string): Promise<string> => {
  try {
    const resp = await restGet(`public_sets?code=eq.${encodeURIComponent(code)}&select=name&limit=1`);
    if (resp.ok) {
      const rows = (await resp.json()) as Array<{ name: string }>;
      if (rows[0]?.name) return rows[0].name;
    }
  } catch {
    // fall through
  }
  return TIER_LIST_PREVIEW_SETS[code]?.name ?? mtgoSetName(code);
};

// Episodes span sets that never reached the leaderboard, so resolve their display name
// from public_episodes instead of public_sets. Null means no episode carries that code.
const fetchEpisodeSetName = async (code: string): Promise<string | null> => {
  try {
    const resp = await restGet(`public_episodes?set_code=eq.${encodeURIComponent(code)}&select=set_name&limit=1`);
    if (resp.ok) {
      const rows = (await resp.json()) as Array<{ set_name: string | null }>;
      if (rows.length > 0) return rows[0].set_name ?? code;
    }
  } catch {
    // fall through
  }
  return null;
};

const episodeSlugMeta = async (slug: string): Promise<RouteMeta | null> => {
  try {
    const resp = await restGet("public_episodes?select=title,youtube_id,summary");
    if (!resp.ok) return null;
    const rows = (await resp.json()) as Array<{ title: string; youtube_id: string | null; summary: string | null }>;
    for (const row of rows) {
      if (episodeSlugBase(row.title) === slug) {
        const image: ImageIntent = row.youtube_id
          ? { kind: "url", url: `https://i.ytimg.com/vi/${row.youtube_id}/hqdefault.jpg` }
          : null;
        const fallback = row.youtube_id ? EPISODE_WATCH_FALLBACK : EPISODE_LISTEN_FALLBACK;
        return page(row.title, episodeDescription(row.summary) ?? fallback, image);
      }
    }
  } catch {
    // fall through
  }
  return null;
};

const EPISODE_SUMMARY_MAX = 300;
const EPISODE_SUMMARY_MIN = 12;
const EPISODE_BOILERPLATE_MARKERS = [
  "http://", "https://", "bit.ly", "limited level-ups patreon", "llu patreon", "llu tierlist",
  "tierlist:", "limited level-ups discord", "llu discord", "alex's stream", "alex's coaching",
  "limited level-ups podcast", "untappedgg", "set primer playlist", "set review playlist",
];
const EPISODE_TRAILING_LABEL = /\s+[A-Za-z][A-Za-z'\- ]{0,40}:$/;
const EPISODE_TRAILING_TAGS = /(?:\s+#\S+)+$/;
const EPISODE_TIMESTAMP = /^\d{1,2}:\d{2}(:\d{2})?\b/;

const episodeDescription = (summary: string | null): string | null => {
  if (!summary) return null;
  for (const line of summary.split("\n")) {
    const prose = episodeProseFromLine(line);
    if (prose.length >= EPISODE_SUMMARY_MIN) {
      if (prose.length > EPISODE_SUMMARY_MAX) {
        return prose.slice(0, EPISODE_SUMMARY_MAX).replace(/\s+\S*$/, "") + "…";
      }
      return prose;
    }
  }
  return null;
};

const episodeProseFromLine = (line: string): string => {
  let text = line.trim();
  if (!text) return "";
  const lower = text.toLowerCase();
  let cut = text.length;
  for (const marker of EPISODE_BOILERPLATE_MARKERS) {
    const idx = lower.indexOf(marker);
    if (idx >= 0 && idx < cut) cut = idx;
  }
  text = text.slice(0, cut).replace(/\s+/g, " ").trim();
  const hadTags = EPISODE_TRAILING_TAGS.test(text);
  text = text.replace(EPISODE_TRAILING_TAGS, "").trim();
  if (!text || EPISODE_TIMESTAMP.test(text) || text.startsWith("#")) return "";
  if (hadTags && text.length < 40 && !/[.!?]/.test(text)) return "";
  text = text.replace(EPISODE_TRAILING_LABEL, "").trim();
  if (text.endsWith(":")) {
    const terminated = text.match(/^.*[.!?]/);
    text = terminated ? terminated[0] : "";
  }
  return text.replace(/[.\s]+$/, "").trim();
};

// Pod-only custom formats never reach public_sets; their display name lives on the pod events
const fetchPodFormatLabel = async (code: string): Promise<string | null> => {
  try {
    const query = `public_pod_draft_events?set_code=eq.${encodeURIComponent(code)}&format_label=not.is.null&select=format_label&limit=1`;
    const resp = await restGet(query);
    if (resp.ok) {
      const rows = (await resp.json()) as Array<{ format_label: string | null }>;
      if (rows[0]?.format_label) return rows[0].format_label;
    }
  } catch {
    // fall through
  }
  return null;
};

const fetchPlayerName = async (slug: string): Promise<string> => {
  try {
    const resp = await restGet(`public_leaderboard?slug=eq.${encodeURIComponent(slug)}&select=display_name&limit=1`);
    if (resp.ok) {
      const rows = (await resp.json()) as Array<{ display_name: string }>;
      if (rows[0]?.display_name) return rows[0].display_name;
    }
  } catch {
    // fall through to the slug
  }
  return slugToName(slug);
};

const playerMeta = (name: string, slug: string): RouteMeta => ({
  ogTitle: `${name}'s Profile`,
  tabTitle: `${name}${TITLE_SEPARATOR}${SITE}`,
  siteName: SITE,
  description: `View ${name}'s drafts on the Limited Level-Ups community website`,
  image: { kind: "avatarProxy", slug },
});

const resolveMeta = async (pathname: string): Promise<RouteMeta> => {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 0) {
    return HOME_META;
  }
  const [section, ...rest] = segments;

  if (section === "player" && rest[0]) {
    return playerMeta(await fetchPlayerName(rest[0]), rest[0]);
  }

  if (section === "leaderboard") {
    if (rest.length === 0) {
      return page("Leaderboard", LEADERBOARD_DESCRIPTION);
    }
    if (rest[0] === "about") {
      return page("About", "Learn how the community leaderboard works");
    }
    if (rest[0] === "player" && rest[1]) {
      return playerMeta(await fetchPlayerName(rest[1]), rest[1]);
    }
    const setCode = rest[0].toUpperCase();
    if (rest[1] === "player" && rest[2]) {
      return playerMeta(await fetchPlayerName(rest[2]), rest[2]);
    }
    // CUBE is a word, not an acronym, and its boards are virtual CUBE-<SET|VARIANT> codes; render
    // "Cube" / "Cube SOS" / the cube's own name, resolving the symbol from the base CUBE set.
    const baseCode = setCode.startsWith("CUBE-") ? "CUBE" : setCode;
    const variant = cubeVariantForBoard(setCode);
    const label = setCode === "CUBE" ? "Cube"
      : variant ? variant.name
      : setCode.startsWith("CUBE-") ? `Cube ${setCode.slice("CUBE-".length)}`
      : setCode;
    const setName = variant?.name ?? await fetchSetName(baseCode);
    return page(
      `${label} Leaderboard`,
      `Check ${setName} ranks and trophies on the leaderboard`,
      { kind: "setSymbol", code: baseCode },
    );
  }

  if (section === "tier-list") {
    if (rest[0]) {
      const setCode = rest[0].toUpperCase();
      const setName = await fetchSetName(setCode);
      if (rest[1] === "archetypes" && skeletonsFor(setCode).length > 0) {
        return page(
          `${setCode} Archetype Skeletons`,
          `Check the cards at the core of every color pair in ${setName}`,
          { kind: "setSymbol", code: setCode },
        );
      }
      return page(
        `${setCode} Tier List`,
        `Check updated Set Review grades for ${setName}`,
        { kind: "setSymbol", code: setCode },
      );
    }
    return page("Tier List", "Check updated Set Review grades for every set");
  }

  if (section === "pods") {
    if (rest[0]) {
      const setCodes = await fetchSetCodes();
      const code = rest[0].toUpperCase();
      if (setCodes.has(code)) {
        const setName = await fetchSetName(code);
        return page(`${code} Pod Drafts`, `${setName} pod draft results and standings`, { kind: "setSymbol", code });
      }
      const formatLabel = await fetchPodFormatLabel(code);
      if (formatLabel) {
        return page(`${code} Pod Drafts`, `${formatLabel} pod draft results and standings`, { kind: "setSymbol", code });
      }
      return page(titleCaseSlug(rest[0], setCodes), "Check seats, logs & replays for this pod draft");
    }
    return page("Pod Drafts", "Check community pod draft results and standings");
  }

  if (section === "p0p1") {
    return p0p1Meta(rest[0]);
  }
  if (section === "episodes") {
    const slug = rest[0];
    if (!slug) {
      return page("Episodes", "Check out the latest episodes, or search the archive");
    }
    if (rest[1]) {
      const meta = await episodeSlugMeta(rest[1]);
      return meta ?? page(titleCaseSlug(rest[1], new Set()), EPISODE_WATCH_FALLBACK);
    }
    if (slug === "shorts") {
      return page("Shorts", "Quick limited tips and highlights in under two minutes");
    }
    if (slug === "audio") {
      return page("Audio", "Listen to the podcast archive");
    }
    const category = categoryFromSlug(slug);
    if (category) {
      return page(`${category} Episodes`, EPISODE_CATEGORY_DESCRIPTIONS[category]);
    }
    const setCode = slug.toUpperCase();
    const setName = await fetchEpisodeSetName(setCode);
    if (setName) {
      return page(
        `${setCode} Episodes`,
        `Episodes, set reviews and draft guides for ${setName}`,
        { kind: "setSymbol", code: setCode },
      );
    }
    const episodeMeta = await episodeSlugMeta(slug);
    return episodeMeta ?? page(titleCaseSlug(slug, new Set()), EPISODE_WATCH_FALLBACK);
  }
  if (section === "community") {
    return page("Community", "Learn about us, the show and the community behind it");
  }
  if (section === "about") {
    return page("About", "Learn how the community leaderboard works");
  }

  return { ...HOME_META, description: null };
};

export const onRequest: PagesFunction = async (context) => {
  const url = new URL(context.request.url);
  // exact host only, so <branch>.dischord.pages.dev previews still serve real content
  if (url.hostname === "dischord.pages.dev") {
    return Response.redirect(`https://limitedlevelups.com${url.pathname}${url.search}`, 302);
  }
  if (context.request.method !== "GET") return context.next();

  const lastSegment = url.pathname.split("/").pop() ?? "";
  if (lastSegment.includes(".") || url.pathname.startsWith("/api/")) return context.next();

  const indexUrl = new URL("/index.html", url.origin);
  const indexResp = await context.env.ASSETS.fetch(indexUrl.toString());

  const meta = await resolveMeta(url.pathname);
  const ogUrl = `${url.origin}${url.pathname}`;
  const isMetaCrawler = /whatsapp|facebookexternalhit/i.test(context.request.headers.get("user-agent") ?? "");
  const image = isMetaCrawler ? metaCrawlerImage(meta.image, url.origin) : meta.image;
  const imageUrl = await resolveImageUrl(image, url.origin, context.env.ASSETS);

  const setContent = (value: string): HTMLRewriterElementContentHandlers => ({
    element: (el) => el.setAttribute("content", value),
  });
  const setHref = (value: string): HTMLRewriterElementContentHandlers => ({
    element: (el) => el.setAttribute("href", value),
  });
  const remove: HTMLRewriterElementContentHandlers = { element: (el) => el.remove() };

  const descriptionHandler = meta.description === null ? remove : setContent(meta.description);
  const siteNameHandler = meta.siteName === null ? remove : setContent(meta.siteName);

  const headers = new Headers(indexResp.headers);
  headers.set("Cache-Control", "public, max-age=0, must-revalidate");
  headers.set("Vary", "User-Agent");
  const baseResponse = new Response(indexResp.body, { status: 200, headers });

  let rewriter = new HTMLRewriter()
    .on("title", { element: (el) => el.setInnerContent(meta.tabTitle) })
    .on('link[rel="canonical"]', setHref(ogUrl))
    .on('meta[property="og:site_name"]', siteNameHandler)
    .on('meta[property="og:title"]', setContent(meta.ogTitle))
    .on('meta[name="twitter:title"]', setContent(meta.ogTitle))
    .on('meta[property="og:url"]', setContent(ogUrl))
    .on('meta[name="description"]', descriptionHandler)
    .on('meta[property="og:description"]', descriptionHandler)
    .on('meta[name="twitter:description"]', descriptionHandler);

  const dimensionHandler = isMetaCrawler ? setContent(String(META_CRAWLER_THUMB_SIZE)) : remove;

  if (imageUrl) {
    rewriter = rewriter
      .on('meta[property="og:image"]', setContent(imageUrl))
      .on('meta[name="twitter:image"]', setContent(imageUrl))
      .on('meta[property="og:image:width"]', dimensionHandler)
      .on('meta[property="og:image:height"]', dimensionHandler)
      .on('meta[property="og:image:alt"]', setContent(meta.ogTitle));
  }

  return rewriter.transform(baseResponse);
};

// Untapped's value; a small declared square makes WhatsApp render the compact thumbnail instead of a full-bleed square
const META_CRAWLER_THUMB_SIZE = 245;

// Meta crawlers (WhatsApp, FB) flatten transparency to white and lose white-on-transparent set symbols; serve the opaque logo, keep opaque avatars
const metaCrawlerImage = (image: ImageIntent, origin: string): ImageIntent => {
  if (image !== null && (image.kind === "url" || image.kind === "avatarProxy")) return image;
  return { kind: "url", url: `${origin}/llu-logo.png` };
};

const resolveImageUrl = async (image: ImageIntent, origin: string, assets: Fetcher): Promise<string | null> => {
  if (image === null) return null;
  if (image.kind === "url") return image.url;
  if (image.kind === "avatarProxy") return `${origin}/api/avatar/${encodeURIComponent(image.slug)}.png`;
  const candidate = `${origin}/set-symbols/${image.code.toLowerCase()}.png`;
  try {
    const resp = await assets.fetch(candidate);
    return resp.ok ? candidate : null;
  } catch {
    return null;
  }
};
