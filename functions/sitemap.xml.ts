import { TIER_LIST_PREVIEW_SETS, hasTierList } from "../frontend/src/data/constants";
import { EPISODE_CATEGORIES, categoryFor, categorySlug, episodeSlugBase } from "../frontend/src/data/episodes";
import { CUBE_VARIANTS, cubeBoardCode } from "../frontend/src/data/cubeVariants";
import { CUBE_BASE, isCubeCode } from "../frontend/src/data/utils";
import { currentSeason, podSeasons, seasonForDate } from "../frontend/src/data/podSeasons";
import { hasCardData } from "../frontend/src/data/podCards";
import { skeletonsFor } from "../frontend/src/data/skeletons";
import { resolveAllContestChips, resolveFeaturedContest } from "../frontend/src/data/p0p1Slots";
import { SET_ROWS_QUERY, type SetRow, restGet, toSetSummary } from "./_shared/public-data";

type EpisodeRow = { title: string; category: string | null; set_code: string | null };
type CubeBoardRow = { set_code: string; kind: string; last_event: string | null };
type PodEventRow = { slug: string; set_code: string; format_label: string | null; kind: string; event_date: string };

export const onRequest: PagesFunction = async (context) => {
  const origin = new URL(context.request.url).origin;
  const [sets, episodes, cubeBoards, podEvents, playerSlugs] = await Promise.all([
    fetchAll<SetRow>(SET_ROWS_QUERY),
    fetchAll<EpisodeRow>("public_episodes?select=title,category,set_code&order=guid"),
    fetchAll<CubeBoardRow>("public_cube_seasons?select=set_code,kind,last_event&order=set_code"),
    fetchAll<PodEventRow>("public_pod_draft_events?select=slug,set_code,format_label,kind,event_date&order=event_id"),
    fetchPlayerSlugs(),
  ]);

  const staticPaths = [
    "/", "/leaderboard", "/leaderboard/about", "/episodes", "/tier-list", "/community", "/pods", "/pods/guide", "/p0p1",
  ];
  const paths = new Set([
    ...staticPaths,
    ...leaderboardPaths(sets, cubeBoards),
    ...playerSlugs.map((slug) => `/player/${slug}`),
    ...episodePaths(episodes),
    ...tierListPaths(sets),
    ...p0p1Paths(),
    ...podPaths(sets, podEvents),
  ]);

  const urls = [...paths].map((path) => `  <url><loc>${escapeXml(encodeURI(origin + path))}</loc></url>`).join("\n");
  const body = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>
`;

  return new Response(body, {
    headers: {
      "content-type": "application/xml; charset=utf-8",
      "cache-control": "public, max-age=3600",
    },
  });
};

const fetchAll = async <T>(query: string): Promise<T[]> => {
  const pageRows = 1000;
  const rows: T[] = [];
  try {
    for (let offset = 0; ; offset += pageRows) {
      const resp = await restGet(`${query}&limit=${pageRows}&offset=${offset}`, 3600);
      if (!resp.ok) {
        return [];
      }
      const page = (await resp.json()) as T[];
      rows.push(...page);
      if (page.length < pageRows) {
        return rows;
      }
    }
  } catch {
    return [];
  }
};

const fetchPlayerSlugs = async (): Promise<string[]> => {
  const [leaderboard, pods] = await Promise.all([
    fetchAll<{ slug: string }>("public_leaderboard?select=slug&order=slug"),
    fetchAll<{ slug: string }>("public_pod_scoring?select=slug&order=slug"),
  ]);
  const slugs = new Set<string>();
  for (const row of [...leaderboard, ...pods]) {
    if (row.slug) {
      slugs.add(row.slug);
    }
  }
  return [...slugs];
};

const leaderboardPaths = (sets: SetRow[], cubeBoards: CubeBoardRow[]): string[] => {
  const paths: string[] = [];
  for (const set of sets) {
    if (!set.is_active && set.code !== CUBE_BASE) {
      paths.push(`/leaderboard/${set.code.toUpperCase()}`);
    }
  }
  const playedCubes = new Set<string>();
  for (const board of cubeBoards) {
    if (board.kind === "variant" && board.last_event) {
      playedCubes.add(board.set_code);
    }
  }
  for (const variant of CUBE_VARIANTS) {
    const code = cubeBoardCode(variant.slug);
    if (playedCubes.has(code)) {
      paths.push(`/leaderboard/${code}`);
    }
  }
  return paths;
};

const episodePaths = (episodes: EpisodeRow[]): string[] => {
  const paths = EPISODE_CATEGORIES.map((category) => `/episodes/${categorySlug(category)}`);
  const setCodes = new Set<string>();
  for (const episode of episodes) {
    if (episode.set_code) {
      setCodes.add(episode.set_code.toLowerCase());
    }
  }
  for (const code of setCodes) {
    paths.push(`/episodes/${code}`);
  }
  for (const episode of episodes) {
    const category = categoryFor(episode.title, episode.category);
    paths.push(`/episodes/${categorySlug(category)}/${episodeSlugBase(episode.title)}`);
  }
  return paths;
};

const tierListPaths = (sets: SetRow[]): string[] => {
  const codes = new Set([...sets.map((set) => set.code.toUpperCase()), ...Object.keys(TIER_LIST_PREVIEW_SETS)]);
  const paths: string[] = [];
  for (const code of codes) {
    if (!hasTierList(code)) {
      continue;
    }
    paths.push(`/tier-list/${code}`);
    if (skeletonsFor(code).length > 0) {
      paths.push(`/tier-list/${code}/archetypes`);
    }
  }
  return paths;
};

const p0p1Paths = (): string[] => {
  const now = Date.now();
  const featuredCode = resolveFeaturedContest(now)?.code;
  const paths: string[] = [];
  for (const contest of resolveAllContestChips(now)) {
    if (contest.status !== "pre" && contest.code !== featuredCode) {
      paths.push(`/p0p1/${contest.code.toLowerCase()}`);
    }
  }
  return paths;
};

const podPaths = (sets: SetRow[], podEvents: PodEventRow[]): string[] => {
  const summaries = sets.map(toSetSummary);
  const boards = podBoards(podEvents);
  const played = new Set(boards.keys());
  for (const event of podEvents) {
    const season = seasonForDate(summaries, event.event_date);
    if (season) {
      played.add(season.code);
    }
  }
  const seasons = podSeasons(summaries).filter((season) => played.has(season.code));
  const seasonCodes = new Set(seasons.map((season) => season.code));
  const current = currentSeason(summaries);
  const homeCode = current && seasonCodes.has(current.code) ? current.code : seasons[0]?.code;

  const paths: string[] = [];
  for (const season of seasons) {
    if (season.code !== homeCode) {
      paths.push(`/pods/${season.code}`);
    }
  }
  const setCodes = new Set(sets.map((set) => set.code));
  for (const [code, board] of boards) {
    if (!seasonCodes.has(code) && linksAsBoard(code, board, setCodes)) {
      paths.push(`/pods/${code}`);
    }
    if (hasCardData(code)) {
      paths.push(`/pods/${code}/data`);
    }
  }
  for (const event of podEvents) {
    paths.push(`/pods/${event.slug}`);
  }
  return paths;
};

type PodBoard = { label: string | null; events: number };

const podBoards = (podEvents: PodEventRow[]): Map<string, PodBoard> => {
  const boards = new Map<string, PodBoard>();
  for (const event of podEvents) {
    const board = boards.get(event.set_code) ?? { label: null, events: 0 };
    board.label = board.label ?? event.format_label;
    if (event.kind !== "mock") {
      board.events += 1;
    }
    boards.set(event.set_code, board);
  }
  return boards;
};

const linksAsBoard = (code: string, board: PodBoard, setCodes: Set<string>): boolean => {
  if (setCodes.has(code) || board.label === null) {
    return isCubeCode(code);
  }
  const minBoardPods = 2;
  return board.events >= minBoardPods;
};

const escapeXml = (value: string): string =>
  value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/'/g, "&apos;")
    .replace(/"/g, "&quot;");
