import { SITE_BLURB_PARAGRAPHS, SITE_LINKS } from "../frontend/src/data/site";
import {
  POD_DRAFTS_DESCRIPTION,
  POD_DRAFTS_TITLE,
  POD_GUIDE_DESCRIPTION,
  POD_GUIDE_TITLE,
} from "../frontend/src/data/podPageMeta";
import { POD_FAQ, POD_INTRO, POD_STEPS, podCrawlLinks } from "./_shared/crawl-text";

export const onRequest: PagesFunction = async (context) => {
  const origin = new URL(context.request.url).origin;
  const body = [
    "# Limited Level-Ups",
    "",
    `> ${SITE_BLURB_PARAGRAPHS[0]}`,
    "",
    `## ${POD_DRAFTS_TITLE}`,
    "",
    ...POD_INTRO.flatMap((paragraph) => [paragraph, ""]),
    ...POD_STEPS.map((step, index) => `${index + 1}. ${step}`),
    "",
    `- [${POD_DRAFTS_TITLE}](${origin}/pods): ${POD_DRAFTS_DESCRIPTION}`,
    `- [${POD_GUIDE_TITLE}](${origin}/pods/guide): ${POD_GUIDE_DESCRIPTION}`,
    ...podCrawlLinks(origin).map(({ label, url }) => `- [${label}](${url})`),
    "",
    "### FAQ",
    "",
    ...POD_FAQ.flatMap(({ question, answer }) => [`**${question}**`, answer, ""]),
    "## Site",
    "",
    `- [Leaderboard](${origin}/leaderboard)`,
    `- [Tier List](${origin}/tier-list)`,
    `- [Episodes](${origin}/episodes)`,
    `- [Community](${origin}/community)`,
    `- [Discord](${SITE_LINKS.discord})`,
    `- [YouTube](${SITE_LINKS.youtube})`,
    "",
  ].join("\n");

  return new Response(body, {
    headers: {
      "content-type": "text/markdown; charset=utf-8",
      "cache-control": "public, max-age=3600",
    },
  });
};
