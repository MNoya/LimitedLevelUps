import { GiProgression, GiRoundTable } from "react-icons/gi";
import {
  ClipboardList,
  GraduationCap,
  type LucideIcon,
  MessagesSquare,
  Rocket,
  TrendingUp,
  Trophy,
  Users,
  Wrench,
} from "lucide-react";
import type { IconType } from "react-icons";
import { FaYoutube } from "react-icons/fa";
import { POD_DRAFT_CHANNEL_NAME, POD_DRAFT_CHANNEL_URL } from "./site";
import { categorySlug, type EpisodeCategory } from "./episodes";
import { useDiscordStats } from "./hooks";
import { DISCORD_BLURB, SITE_BLURB_PARAGRAPHS } from "./site";

export const COMMUNITY_DISCORD_PITCH = DISCORD_BLURB.replace("The Limited Level-Ups Discord is a ", "A ");

export const COMMUNITY_DISCORD_HEADING = "A home for Limited players";

export const COMMUNITY_INTRO_PARAGRAPHS = [
  SITE_BLURB_PARAGRAPHS[0],
  "Whether you're looking to get your first trophy, sharpen your fundamentals, or compete at the highest level, " +
    "you'll find a community of Limited enthusiasts ready to help you level up your game.",
];

export interface CommunityHighlight {
  Icon: LucideIcon;
  text: string;
}

export const COMMUNITY_HIGHLIGHTS: CommunityHighlight[] = [
  { Icon: MessagesSquare, text: "Discuss the latest formats and upcoming sets" },
  { Icon: TrendingUp, text: "Get help with deckbuilding, picks, and gameplay" },
  { Icon: Rocket, text: "Play in community organized events" },
  { Icon: Trophy, text: "Connect with dedicated Limited players" },
];

export const COMMUNITY_SHOW_PARAGRAPHS = [
  "Every set covered from start to finish: first impressions as previews drop, a complete set review, then " +
    "metagame updates as it develops.",
  "Other episodes range from focused deck breakdowns to evergreen lessons on gameplay and big picture strategy " +
    "that stay relevant from one format to the next.",
];

export const COMMUNITY_SUPPORT_NOTE =
  "Enjoying the show and want to support it? The Patreon rewards are all about getting you better at Limited, with " +
  "hands-on help that goes beyond the episodes.";

export const COMMUNITY_SUPPORT_REWARDS: Array<{ Icon: LucideIcon; label: string }> = [
  { Icon: Wrench, label: "Deck tech help" },
  { Icon: ClipboardList, label: "Draft log review" },
  { Icon: Users, label: "Group classes" },
  { Icon: GraduationCap, label: "1-on-1 coaching" },
];

export const COMMUNITY_SHOW_TOPICS: Array<{
  category: EpisodeCategory;
  label: string;
  Icon?: IconType;
  iconClassName?: string;
}> = [
  { category: "Set Review", label: "Set reviews" },
  { category: "Metagame", label: "Format updates" },
  { category: "Draft", label: "Draft videos", Icon: FaYoutube, iconClassName: "text-red" },
  { category: "Evergreen", label: "Evergreen episodes" },
];

export interface CommunityLink {
  title: string;
  live?: boolean;
  steps: readonly string[];
  to: string;
  cta: string;
  Icon: IconType;
}

export const COMMUNITY_EVENTS: CommunityLink[] = [
  {
    title: "Community leaderboard",
    live: true,
    steps: [
      "Type /join on Discord to link your 17lands profile",
      "Share your trophies and records across sets and formats",
      "See the drafts and decks members are winning with",
    ],
    to: "/leaderboard",
    cta: "View the leaderboard",
    Icon: GiProgression,
  },
  {
    title: "Daily pod drafts",
    steps: [
      `Sign up for the next draft in [${POD_DRAFT_CHANNEL_NAME}](${POD_DRAFT_CHANNEL_URL})`,
      "Draft together using [Draftmancer](draftmancer.com) and play the matches live on MTGA",
      "All seats, logs and replays are saved on the site to revisit anytime",
    ],
    to: "/pods",
    cta: "Check past & upcoming events",
    Icon: GiRoundTable,
  },
];

export function useCommunityStats(): { members?: number; online?: number } {
  const { data } = useDiscordStats();
  return { members: data?.memberCount, online: data?.onlineCount };
}

export function categoryHref(category: EpisodeCategory): string {
  return `/episodes/${categorySlug(category)}`;
}
