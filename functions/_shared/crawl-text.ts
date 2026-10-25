import {
  COMMUNITY_DISCORD_HEADING,
  COMMUNITY_INTRO_PARAGRAPHS,
  COMMUNITY_SHOW_PARAGRAPHS,
  DISCORD_BLURB,
  HOSTS,
  SITE_BLURB_PARAGRAPHS,
  SITE_LINKS,
} from "../../frontend/src/data/site";
import { SITE_NAME } from "../../frontend/src/data/constants";
import { POD_DRAFTS_TITLE } from "../../frontend/src/data/podPageMeta";

type PodCrawlLink = { label: string; url: string };

export const POD_INTRO = [
  "Pod Drafts are a way to play drafts outside of the normal Arena queue and ladder systems. You draft with others on "
  + "Draftmancer then play out the matches against the people you drafted with. No gems wasted and you get to play "
  + "other strong limited players and discuss your draft and matches if you want.",
  "The whole thing is automated through a Discord bot and integrates with the Limited Level-Ups website so you can see "
  + "all the decks, draft logs and even replays of both sides of each private match. All of this also counts for "
  + "leaderboards and shows on your personal page.",
];

export const POD_STEPS = [
  "Join the Discord and sign up for any draft time that works for you.",
  "Draft on Draftmancer when the table link is posted, then press Export to copy your deck into Arena.",
  "Play your matches on MTG Arena as a Limited Tournament Match and report each result in Discord.",
];

export const POD_FAQ: { question: string; answer: string }[] = [
  {
    question: "Are Pod Drafts free?",
    answer:
      "All you need is 2~3 hours and having collected the set or some wildcards to craft what you don't already own. "
      + "Once you draft a set 20 times, as many invested Limited players do, it takes 0 wildcards to play it anytime. "
      + "Peasant Cube is only commons and uncommons, very nice for players without a deep MTGA collection.",
  },
  {
    question: "When are the pods?",
    answer:
      "Pod drafts of the new format run every day, scheduled for 2PM ET for the European-friendly Early Pod and 9PM ET "
      + "for the Late Pod aimed at NA. Discord localizes timestamps to your own timezone. Off-season, the schedule "
      + "adds flashbacks of popular formats and Peasant Cube.",
  },
  {
    question: "How many players does a pod need?",
    answer:
      "A pod aims for 8 players and needs at least 6. Pods of 6 play Team Draft, pods of 8 to 10 play Swiss, and "
      + "larger groups split into separate tables.",
  },
  {
    question: "Are matches Bo1 or Bo3?",
    answer: "BO3 matches, 3 rounds, paired by record, just like a Trad Draft on Arena.",
  },
  { question: "What if I draft more than 4 copies of a card?", answer: "Limited decks let you do this just fine." },
  { question: "How do I leave a pod I joined?", answer: "Press Leave on the daily pod launcher in the pod channel." },
];

export const podCrawlLinks = (origin: string): PodCrawlLink[] => [
  { label: "Join the Pod Drafts on Discord", url: SITE_LINKS.discordPods },
  {
    label: "Video walkthrough by Chord_O_Calls: How to Draft For Free with the LLU Community",
    url: `${origin}/episodes/evergreen/how-to-draft-for-free-with-the-llu-community`,
  },
  { label: "Walkthrough on YouTube", url: "https://www.youtube.com/watch?v=WmYZgprpxOc" },
];

export const crawlArticle = (innerHtml: string): string => {
  const visuallyHidden =
    "position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);border:0";
  return `<article style="${visuallyHidden}">${innerHtml}</article>`;
};

export const podCrawlHtml = (heading: string): string => {
  const intro = POD_INTRO.map((paragraph) => `<p>${paragraph}</p>`).join("");
  const steps = POD_STEPS.map((step) => `<li>${step}</li>`).join("");
  const faq = POD_FAQ.map(({ question, answer }) => `<h3>${question}</h3><p>${answer}</p>`).join("");
  const guideLink = { label: "Pod Drafts guide", url: "/pods/guide" };
  const links = linkList([guideLink, ...podCrawlLinks("")]);
  return `<h1>${heading}</h1>${intro}<h2>How to play</h2><ol>${steps}</ol><h2>FAQ</h2>${faq}<h2>Links</h2>${links}`;
};

export const homeCrawlHtml = (): string =>
  `<h1>${SITE_NAME}</h1>${paragraphs(SITE_BLURB_PARAGRAPHS)}<h2>Discord</h2><p>${escapeHtml(DISCORD_BLURB)}</p>`
  + showAndHostsHtml();

export const communityCrawlHtml = (): string =>
  `<h1>${COMMUNITY_DISCORD_HEADING}</h1>${paragraphs(COMMUNITY_INTRO_PARAGRAPHS)}${showAndHostsHtml()}`;

export type PodEventSummary = {
  name: string;
  formatName: string;
  date: string;
  playerCount: number;
  rounds: number;
  isTeamDraft: boolean;
  championName: string | null;
  championSlug: string | null;
  championRecord: string | null;
};

export const podEventCrawlHtml = (event: PodEventSummary): string => {
  const style = event.isTeamDraft ? "Team Draft" : `${event.rounds} rounds of Swiss`;
  const played = event.playerCount > 0
    ? `${event.formatName} pod draft on ${event.date} with ${event.playerCount} players, ${style}.`
    : `${event.formatName} pod draft scheduled for ${event.date}.`;
  let result = "";
  if (event.championName && event.championSlug) {
    const profileUrl = `/player/${encodeURIComponent(event.championSlug)}`;
    const champion = `<a href="${profileUrl}">${escapeHtml(event.championName)}</a>`;
    const record = event.championRecord ? ` ${escapeHtml(event.championRecord)}` : "";
    result = ` ${champion} won${record}.`;
  }
  const links = linkList([
    { label: POD_DRAFTS_TITLE, url: "/pods" },
    { label: "Pod Drafts guide", url: "/pods/guide" },
  ]);
  return `<h1>${escapeHtml(event.name)}</h1><p>${escapeHtml(played)}${result}</p>${links}`;
};

const showAndHostsHtml = (): string => {
  const hosts = HOSTS.map((host) => {
    const heading = escapeHtml(`${host.name}, ${host.role}`);
    return `<h3>${heading}</h3><p>${escapeHtml(host.bio)}</p>`;
  });
  const links = linkList([
    { label: POD_DRAFTS_TITLE, url: "/pods" },
    { label: "Leaderboard", url: "/leaderboard" },
    { label: "Tier List", url: "/tier-list" },
    { label: "Episodes", url: "/episodes" },
    { label: "Community", url: "/community" },
    { label: "Discord", url: SITE_LINKS.discord },
    { label: "YouTube", url: SITE_LINKS.youtube },
    { label: "Patreon", url: SITE_LINKS.patreon },
  ]);
  return `<h2>The show</h2>${paragraphs(COMMUNITY_SHOW_PARAGRAPHS)}<h2>Hosts</h2>${hosts.join("")}`
    + `<h2>Links</h2>${links}`;
};

const paragraphs = (texts: string[]): string => texts.map((text) => `<p>${escapeHtml(text)}</p>`).join("");

const linkList = (links: PodCrawlLink[]): string =>
  `<ul>${links.map(({ label, url }) => `<li><a href="${url}">${label}</a></li>`).join("")}</ul>`;

const escapeHtml = (text: string): string =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
