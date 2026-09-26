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
  IDENTITY_VIEWS,
  SITE_NAME as SITE,
  TIER_LIST_PREVIEW_SETS,
  TITLE_SEPARATOR,
  hasTierList,
} from "../frontend/src/data/constants";
import { cardDataLabel, hasCardData } from "../frontend/src/data/podCards";
import { isMtgoFlashbackCode, mtgoSetName } from "../frontend/src/data/mtgoSets";
import {
  type FeaturedContest,
  resolveContestByCode,
  resolveFeaturedContest,
} from "../frontend/src/data/p0p1Slots";
import { categoryFromSlug, episodeSlugBase } from "../frontend/src/data/episodes";
import { cubeForBoard, cubeVariantForBoard } from "../frontend/src/data/cubeVariants";
import { CUBE_LIFETIME, isCubeSeasonCode } from "../frontend/src/data/utils";
import { podSeasons } from "../frontend/src/data/podSeasons";
import { skeletonsFor } from "../frontend/src/data/skeletons";
import {
  SET_ROWS_QUERY,
  type SetRow,
  restGet,
  restRows,
  toSetSummary,
} from "./_shared/public-data";

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
const TRANSCRIPT_READ_DESCRIPTION = "Read this episode";

const LEADERBOARD_DESCRIPTION =
  "Check ranks and trophies from the community. /join on Discord to share your drafts and climb the leaderboard";
const HOME_DESCRIPTION = "Weekly episodes, set reviews, strategy and community events. Join the Discord and climb the leaderboard.";

const P0P1_PICK_SENTENCE = "Pick a team of eight cards you think will perform best from the upcoming set.";

// A bare /p0p1 unfurls whichever contest is featured; /p0p1/<code> unfurls that one, so an archive
// link carries its own set symbol instead of the live contest's.
const p0p1Meta = (contest: FeaturedContest | null, now: number): RouteMeta => {
  if (contest === null) {
    return page("P0P1 Challenge", P0P1_PICK_SENTENCE);
  }

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
  noImagePreview?: boolean;
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

const META_CACHE_TTL = 600;

// Episodes span sets that never reached the leaderboard, so resolve their display name
// from public_episodes instead of public_sets. Null means no episode carries that code.
const fetchEpisodeSetName = async (code: string): Promise<string | null> => {
  try {
    const query = `public_episodes?set_code=eq.${encodeURIComponent(code)}&select=set_name&limit=1`;
    const resp = await restGet(query, META_CACHE_TTL);
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
    const resp = await restGet("public_episodes?select=title,youtube_id,summary", META_CACHE_TTL);
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

const playerMeta = (name: string, slug: string): RouteMeta => ({
  ogTitle: `${name}'s Profile`,
  tabTitle: `${name}${TITLE_SEPARATOR}${SITE}`,
  siteName: SITE,
  description: `View ${name}'s drafts on the Limited Level-Ups community website`,
  image: { kind: "avatarProxy", slug },
});

export const onRequest: PagesFunction = async (context) => {
  const url = new URL(context.request.url);
  // exact host only, so <branch>.dischord.pages.dev previews still serve real content
  if (url.hostname === "dischord.pages.dev") {
    return Response.redirect(`https://limitedlevelups.com${url.pathname}${url.search}`, 302);
  }
  if (context.request.method !== "GET") return context.next();

  const lastSegment = url.pathname.split("/").pop() ?? "";
  if (lastSegment.includes(".") || url.pathname.startsWith("/api/")) return context.next();

  const route = await resolveRoute(url.pathname.split("/").filter(Boolean));
  if (route.kind === "redirect") {
    return Response.redirect(`${url.origin}${route.location}${url.search}`, route.status);
  }
  const { meta } = route;

  const indexUrl = new URL("/index.html", url.origin);
  const indexResp = await context.env.ASSETS.fetch(indexUrl.toString());

  const ogUrl = `${url.origin}${route.canonicalPath}`;
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
  const baseResponse = new Response(indexResp.body, { status: route.notFound ? 404 : 200, headers });

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

  if (meta.noImagePreview) {
    rewriter = rewriter.on("head", {
      element: (el) => el.append('<meta name="robots" content="max-image-preview:none">', { html: true }),
    });
  }

  if (route.notFound) {
    rewriter = rewriter.on("head", {
      element: (el) => el.append('<meta name="robots" content="noindex">', { html: true }),
    });
  }

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

type RouteResolution =
  | { kind: "page"; meta: RouteMeta; canonicalPath: string; notFound: boolean }
  | { kind: "redirect"; location: string; status: 301 | 302 };

const resolved = (meta: RouteMeta, canonicalPath: string, notFound = false): RouteResolution => ({
  kind: "page",
  meta,
  canonicalPath,
  notFound,
});

const redirect = (location: string, status: 301 | 302): RouteResolution => ({ kind: "redirect", location, status });

const resolveRoute = async (segments: string[]): Promise<RouteResolution> => {
  if (segments.length === 0) {
    return resolved({ ...HOME_META, noImagePreview: true }, "/");
  }
  const legacyPath = legacyRedirectPath(segments);
  if (legacyPath) {
    return redirect(legacyPath, 301);
  }
  if (!matchesAppRoute(segments)) {
    return resolved({ ...HOME_META, description: null }, `/${segments.join("/")}`, true);
  }
  const section = segments[0].toLowerCase();
  const rest = segments.slice(1);

  if (section === "player") {
    return playerRoute(rest[0], rest[1]);
  }
  if (section === "leaderboard") {
    return leaderboardRoute(rest[0]);
  }
  if (section === "tier-list") {
    return tierListRoute(rest);
  }
  if (section === "pods") {
    return podsRoute(rest);
  }
  if (section === "p0p1") {
    return p0p1Route(rest[0]);
  }
  if (section === "episodes") {
    return resolved(await episodesMeta(rest), `/${segments.join("/").toLowerCase()}`);
  }
  if (section === "community") {
    return resolved(page("Community", "Learn about us, the show and the community behind it"), "/community");
  }
  return resolved({ ...HOME_META, description: null }, `/${section}`);
};

const legacyRedirectPath = (segments: string[]): string | null => {
  const section = segments[0].toLowerCase();
  const rest = segments.slice(1).map((segment) => segment.toLowerCase());
  if (rest.length === 0 && section === "about") {
    return "/leaderboard/about";
  }
  if (rest.length === 0 && section === "players") {
    return "/leaderboard";
  }
  if (section !== "leaderboard") {
    return null;
  }
  if (rest.length === 2 && rest[0] === "player") {
    return `/player/${rest[1]}`;
  }
  if (rest.length === 3 && rest[1] === "player") {
    return `/player/${rest[2]}/${rest[0].toUpperCase()}`;
  }
  if (rest[0] === "archetypes" || rest[1] === "archetypes") {
    return "/leaderboard";
  }
  return null;
};

const matchesAppRoute = (segments: string[]): boolean => {
  const appRoutes = [
    "/episodes",
    "/episodes/:categorySlug",
    "/episodes/:categorySlug/:episodeSlug",
    "/community",
    "/leaderboard",
    "/leaderboard/about",
    "/leaderboard/:setCode",
    "/player/:slug",
    "/player/:slug/:setCode",
    "/pods/guide",
    "/pods",
    "/pods/:board/data",
    "/pods/:board/data/:card",
    "/pods/:slug",
    "/pods/:slug/:who",
    "/pods/:slug/:who/:pack/:pick",
    "/tier-list",
    "/tier-list/:setCode",
    "/tier-list/:setCode/archetypes",
    "/tier-list/:setCode/archetypes/:pair",
    "/tier-list/:setCode/:card",
    "/p0p1",
    "/p0p1/:setCode",
    "/banner",
  ];
  for (const route of appRoutes) {
    const parts = route.split("/").filter(Boolean);
    const matches = parts.every((part, i) => part.startsWith(":") || part === segments[i]?.toLowerCase());
    if (matches && parts.length === segments.length) {
      return true;
    }
  }
  return false;
};

const playerRoute = async (rawSlug: string, rawSetCode: string | undefined): Promise<RouteResolution> => {
  const slug = rawSlug.toLowerCase();
  const player = await lookupPlayer(slug);
  const name = player.status === "found" ? player.name : slugToName(slug);
  const canonicalPath = rawSetCode ? `/player/${slug}/${rawSetCode.toUpperCase()}` : `/player/${slug}`;
  return resolved(playerMeta(name, slug), canonicalPath, player.status === "missing");
};

const leaderboardRoute = async (rawCode: string | undefined): Promise<RouteResolution> => {
  if (rawCode === undefined) {
    return resolved(page("Leaderboard", LEADERBOARD_DESCRIPTION), "/leaderboard");
  }
  if (rawCode.toLowerCase() === "about") {
    return resolved(page("About", "Learn how the community leaderboard works"), "/leaderboard/about");
  }
  const setCode = rawCode.toUpperCase();
  const sets = await fetchSets();
  if (sets?.some((set) => set.is_active && set.code === setCode)) {
    return redirect("/leaderboard", 302);
  }
  // CUBE is a word, not an acronym, and its boards are virtual CUBE-<SET|VARIANT> codes; render
  // "Cube" / "Cube SOS" / the cube's own name, resolving the symbol from the base CUBE set.
  const baseCode = setCode.startsWith("CUBE-") ? "CUBE" : setCode;
  const variant = cubeVariantForBoard(setCode);
  const label = setCode === "CUBE" ? "Cube"
    : variant ? variant.name
    : setCode.startsWith("CUBE-") ? `Cube ${setCode.slice("CUBE-".length)}`
    : setCode;
  const setName = variant?.name ?? setNameFor(sets, baseCode);
  const meta = page(
    `${label} Leaderboard`,
    `Check ${setName} ranks and trophies on the leaderboard`,
    { kind: "setSymbol", code: baseCode },
  );
  const boardExists = await leaderboardBoardExists(setCode, sets);
  return resolved(meta, `/leaderboard/${setCode}`, boardExists === false);
};

const tierListRoute = async (rest: string[]): Promise<RouteResolution> => {
  const [rawCode, , rawPair] = rest;
  if (rawCode === undefined) {
    return resolved(page("Tier List", "Check updated Set Review grades for every set"), "/tier-list");
  }
  const setCode = rawCode.toUpperCase();
  const setName = setNameFor(await fetchSets(), setCode);
  const symbol: ImageIntent = { kind: "setSymbol", code: setCode };
  const notFound = !hasTierList(setCode);
  const cardPath = rest.length === 2 && rest[1].toLowerCase() !== "archetypes";
  if (rest.length > 1 && !cardPath && skeletonsFor(setCode).length > 0) {
    const archetypesPath = `/tier-list/${setCode}/archetypes`;
    const description = `Check the cards at the core of every color pair in ${setName}`;
    return resolved(
      page(`${setCode} Archetype Skeletons`, description, symbol),
      rawPair ? `${archetypesPath}/${rawPair.toLowerCase()}` : archetypesPath,
      notFound,
    );
  }
  return resolved(
    page(`${setCode} Tier List`, `Check updated Set Review grades for ${setName}`, symbol),
    cardPath ? `/tier-list/${setCode}/${rest[1].toLowerCase()}` : `/tier-list/${setCode}`,
    notFound,
  );
};

const podsRoute = async (rest: string[]): Promise<RouteResolution> => {
  const [first, second, third] = rest;
  if (first === undefined) {
    return resolved(page("Pod Drafts", "Check community pod draft results and standings"), "/pods");
  }
  if (second?.toLowerCase() === "data" && rest.length <= 3) {
    const board = first.toUpperCase();
    const label = cardDataLabel(board);
    const boardPath = `/pods/${board}/data`;
    return resolved(
      page(`${label} Cube Card Data`, `Card stats from every ${label} Cube pod draft`),
      third ? `${boardPath}/${third}` : boardPath,
      !hasCardData(board),
    );
  }
  if (rest.length === 1 && first.toLowerCase() === "guide") {
    return resolved(page("Pod Drafts Guide", "How to play on our community Pod Drafts"), "/pods/guide");
  }
  return podSlugRoute(first, rest.slice(1));
};

const podSlugRoute = async (rawSlug: string, tail: string[]): Promise<RouteResolution> => {
  const code = rawSlug.toUpperCase();
  const split = rawSlug.lastIndexOf("-");
  const boardQuery = (setCode: string) =>
    `public_pod_draft_events?select=set_code,format_label&set_code=ilike.${queryValue(setCode)}`;
  const [sets, boards, events, windowBoards] = await Promise.all([
    fetchSets(),
    viewRows<PodBoardRow>(`${boardQuery(rawSlug)}&order=format_label.nullslast&limit=1`),
    viewRows<{ slug: string }>(`public_pod_draft_events?select=slug&slug=ilike.${queryValue(rawSlug)}&limit=1`),
    split > 0 ? viewRows<PodBoardRow>(`${boardQuery(rawSlug.slice(0, split))}&limit=1`) : [],
  ]);
  const meta = podSlugMeta(rawSlug, sets, boards?.[0]?.format_label ?? null);
  const event = events?.[0];
  if (tail.length > 0) {
    return resolved(meta, `/pods/${event?.slug ?? rawSlug}/${tail.join("/")}`, events !== null && !event);
  }

  const seasons = podSeasons((sets ?? []).map(toSetSummary));
  const season = seasons.find((s) => s.code === code);
  if (season) {
    return resolved(meta, `/pods/${season.code}`);
  }
  if (boards?.[0]) {
    return resolved(meta, `/pods/${boards[0].set_code}`);
  }
  const windowSeasonCode = rawSlug.slice(split + 1).toUpperCase();
  if (windowBoards?.[0] && seasons.some((s) => s.code === windowSeasonCode)) {
    return resolved(meta, `/pods/${rawSlug.toLowerCase()}`);
  }
  if (event) {
    return resolved(meta, `/pods/${event.slug}`);
  }
  const lookupFailed = sets === null || boards === null || events === null || windowBoards === null;
  return resolved(meta, `/pods/${rawSlug}`, !lookupFailed);
};

const podSlugMeta = (rawSlug: string, sets: SetRow[] | null, formatLabel: string | null): RouteMeta => {
  const code = rawSlug.toUpperCase();
  const set = sets?.find((s) => s.code === code);
  if (set) {
    return page(`${code} Pod Drafts`, `${set.name} pod draft results and standings`, { kind: "setSymbol", code });
  }
  // Pod-only custom formats never reach public_sets; their display name lives on the pod events
  if (formatLabel) {
    return page(`${code} Pod Drafts`, `${formatLabel} pod draft results and standings`, { kind: "setSymbol", code });
  }
  const setCodes = new Set((sets ?? []).map((s) => s.code));
  return page(titleCaseSlug(rawSlug, setCodes), "Check seats, logs & replays for this pod draft");
};

const p0p1Route = (rawCode: string | undefined): RouteResolution => {
  const now = Date.now();
  if (rawCode === undefined) {
    return resolved(p0p1Meta(resolveFeaturedContest(now), now), "/p0p1");
  }
  const contest = resolveContestByCode(rawCode, now);
  const hidden = contest === null || (contest.status === "pre" && !contest.comingSoon);
  return resolved(p0p1Meta(contest, now), `/p0p1/${rawCode.toLowerCase()}`, hidden);
};

const episodesMeta = async (rest: string[]): Promise<RouteMeta> => {
  const slug = rest[0];
  if (!slug) {
    return page("Episodes", "Check out the latest episodes, or search the archive");
  }
  if (slug === "transcripts") {
    if (!rest[1]) {
      return {
        ogTitle: "Episode Transcripts",
        tabTitle: `Transcripts${TITLE_SEPARATOR}${SITE}`,
        siteName: SITE,
        description: "Read the episode library",
        image: null,
      };
    }
    const base = await episodeSlugMeta(rest[1]);
    if (base) {
      return { ...base, description: TRANSCRIPT_READ_DESCRIPTION };
    }
    return page(titleCaseSlug(rest[1], new Set()), TRANSCRIPT_READ_DESCRIPTION);
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

type PodBoardRow = { set_code: string; format_label: string | null };

type PlayerLookup = { status: "found"; name: string } | { status: "missing" } | { status: "failed" };

const lookupPlayer = async (slug: string): Promise<PlayerLookup> => {
  const results = await Promise.all(
    IDENTITY_VIEWS.map((view) =>
      viewRows<{ display_name: string | null }>(`${view}?slug=eq.${queryValue(slug)}&select=display_name&limit=1`),
    ),
  );
  for (const rows of results) {
    if (rows?.[0]) {
      return { status: "found", name: rows[0].display_name ?? slugToName(slug) };
    }
  }
  return results.includes(null) ? { status: "failed" } : { status: "missing" };
};

const leaderboardBoardExists = async (setCode: string, sets: SetRow[] | null): Promise<boolean | null> => {
  if (setCode === CUBE_LIFETIME || isMtgoFlashbackCode(setCode) || cubeForBoard(setCode)) {
    return true;
  }
  if (sets === null) {
    return null;
  }
  if (sets.some((set) => set.code === setCode)) {
    return true;
  }
  if (!isCubeSeasonCode(setCode)) {
    return false;
  }
  const rows = await viewRows<{ set_code: string }>(
    `public_cube_seasons?set_code=eq.${queryValue(setCode)}&select=set_code&limit=1`,
  );
  return rows === null ? null : rows.length > 0;
};

const setNameFor = (sets: SetRow[] | null, code: string): string =>
  sets?.find((set) => set.code === code)?.name ?? TIER_LIST_PREVIEW_SETS[code]?.name ?? mtgoSetName(code);

const fetchSets = (): Promise<SetRow[] | null> => viewRows<SetRow>(SET_ROWS_QUERY);

const viewRows = <T>(query: string): Promise<T[] | null> => restRows<T>(query, META_CACHE_TTL);

const queryValue = (segment: string): string => {
  try {
    return encodeURIComponent(decodeURIComponent(segment));
  } catch {
    return encodeURIComponent(segment);
  }
};
