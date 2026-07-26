import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { usePlayerProfile, useSets } from "../data/hooks";
import { categoryFromSlug } from "../data/episodes";
import { cubeVariantForBoard } from "../data/cubeVariants";
import { ACTIVE_SET_CODE, SITE_NAME, TITLE_SEPARATOR } from "../data/constants";

// Mirrors functions/_middleware.ts so the in-app tab title matches the crawler/unfurl title.
// The SPA never reloads on navigation, so without this the tab title would freeze at whatever
// the first hard load rendered.
export function DocumentTitle() {
  const { pathname } = useLocation();
  const segments = pathname.split("/").filter(Boolean);
  const { data: sets } = useSets();
  const setCodes = new Set((sets ?? []).map((s) => s.code.toUpperCase()));

  const [section, ...rest] = segments;
  const playerSlug = playerSlugFrom(section, rest);
  const setForProfile = (rest[0] && rest[0] !== "player" ? rest[0].toUpperCase() : undefined) ?? ACTIVE_SET_CODE;
  const { data: profile } = usePlayerProfile(playerSlug, setForProfile);

  const pageTitle = resolvePageTitle(segments, profile?.displayName, setCodes);

  useEffect(() => {
    document.title = pageTitle === SITE_NAME ? SITE_NAME : `${pageTitle}${TITLE_SEPARATOR}${SITE_NAME}`;
  }, [pageTitle]);

  return null;
}

const playerSlugFrom = (section: string | undefined, rest: string[]): string | undefined => {
  if (section !== "leaderboard") {
    return undefined;
  }
  if (rest[0] === "player") {
    return rest[1]?.toLowerCase();
  }
  if (rest[1] === "player") {
    return rest[2]?.toLowerCase();
  }
  return undefined;
};

const titleCaseSlug = (slug: string, setCodes: Set<string>): string =>
  slug
    .split("-")
    .map((word) => {
      const upper = word.toUpperCase();
      if (setCodes.has(upper)) {
        return upper;
      }
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");

// Set codes are acronyms (SOS, ECL) so they stay uppercase, but CUBE is a word — render "Cube", its
// seasons as "Cube SOS", and a whole-cube board by the cube's own name ("Arena Cube").
const setTitleLabel = (code: string): string => {
  const upper = code.toUpperCase();
  if (upper === "CUBE") return "Cube";
  const variant = cubeVariantForBoard(upper);
  if (variant) return variant.name;
  if (upper.startsWith("CUBE-")) return `Cube ${upper.slice("CUBE-".length)}`;
  return upper;
};

const resolvePageTitle = (
  segments: string[],
  playerName: string | undefined,
  setCodes: Set<string>,
): string => {
  if (segments.length === 0) {
    return SITE_NAME;
  }
  const [section, ...rest] = segments;

  if (section === "leaderboard") {
    if (rest.length === 0) {
      return "Leaderboard";
    }
    if (rest[0] === "about") {
      return "About";
    }
    if (rest[0] === "player" && rest[1]) {
      return playerName ?? titleCaseSlug(rest[1], setCodes);
    }
    if (rest[1] === "player" && rest[2]) {
      return playerName ?? titleCaseSlug(rest[2], setCodes);
    }
    return `${setTitleLabel(rest[0])} Leaderboard`;
  }

  if (section === "tier-list") {
    return rest[0] ? `${rest[0].toUpperCase()} Tier List` : "Tier List";
  }
  if (section === "pods") {
    return rest[0] ? titleCaseSlug(rest[0], setCodes) : "Pod Drafts";
  }
  if (section === "p0p1" || section === "p0p1-mocks") {
    return "P0P1";
  }
  if (section === "episodes") {
    const slug = rest[0];
    if (!slug) {
      return "Episodes";
    }
    if (slug === "shorts") {
      return "Shorts";
    }
    if (slug === "audio") {
      return "Audio";
    }
    const category = categoryFromSlug(slug);
    if (category) {
      return `${category} Episodes`;
    }
    return `${setTitleLabel(slug)} Episodes`;
  }
  if (section === "community") {
    return "Community";
  }
  if (section === "about") {
    return "About";
  }
  return SITE_NAME;
};
