import { Mic } from "lucide-react";
import { SiPatreon } from "react-icons/si";
import { PageShell } from "../components/PageShell";
import { Container } from "../components/Container";
import { ChamferCta } from "../components/ChamferCta";
import { DiscordIcon } from "../components/BrandIcons";
import { CommunityHeading, HostBlock, EventCard, SectionPanel, ShowTopics, SupportCard } from "../components/CommunityBits";
import {
  COMMUNITY_DISCORD_HEADING,
  COMMUNITY_EVENTS,
  COMMUNITY_HIGHLIGHTS,
  COMMUNITY_INTRO_PARAGRAPHS,
  COMMUNITY_SHOW_PARAGRAPHS,
  COMMUNITY_SHOW_TOPICS,
  useCommunityStats,
} from "../data/community";
import { HOSTS, SITE_LINKS } from "../data/site";

export function CommunityPage() {
  const { members, online } = useCommunityStats();

  return (
    <PageShell subtitle="COMMUNITY">
      <section
        className="border-b border-border"
        style={{ background: "linear-gradient(180deg, #14181f 0%, #0a0c10 100%)" }}
      >
        <Container className="pt-4 pb-10 md:py-10">
          <div className="flex flex-col items-center gap-10 lg:flex-row lg:items-center lg:justify-between lg:gap-12 xl:max-w-[1600px] xl:pr-6">
            <div className="flex flex-col gap-6 max-w-[600px] mx-auto text-center lg:text-left lg:mx-0">
              <h1 className="font-display text-text text-[34px] md:text-[48px] leading-[1.02] tracking-[0.01em]">
                {COMMUNITY_DISCORD_HEADING}
              </h1>
              <div className="flex flex-col gap-4">
                {COMMUNITY_INTRO_PARAGRAPHS.map((paragraph) => (
                  <p key={paragraph.slice(0, 16)} className="text-subtle text-[15px] md:text-[16px] leading-[1.7]">
                    {highlightBrand(paragraph)}
                  </p>
                ))}
              </div>
            </div>
            <div className="flex flex-col items-center gap-8 shrink-0 xl:contents">
              <div className="flex flex-col items-center gap-4 shrink-0">
                <ChamferCta
                  label="JOIN THE DISCHORD"
                  href={SITE_LINKS.discord}
                  target="_blank"
                  size="lg"
                  grow
                  className="whitespace-nowrap"
                  icon={
                    <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-bg text-white shrink-0">
                      <DiscordIcon size={20} />
                    </span>
                  }
                />
                <MemberCount members={members} online={online} />
              </div>
              <div className="shrink-0 flex justify-center">
                <ul className="inline-flex flex-col gap-4">
                  {COMMUNITY_HIGHLIGHTS.map((highlight) => (
                    <li key={highlight.text} className="flex items-center gap-3 text-subtle text-[15px] leading-[1.4]">
                      <highlight.Icon size={18} strokeWidth={2} className="shrink-0 text-muted" />
                      {highlight.text}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </Container>
      </section>

      <Container className="pt-10 py-10 md:pt-12">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {COMMUNITY_EVENTS.map((event) => (
            <EventCard key={event.to} event={event} />
          ))}
          <SectionPanel
            title={
              <span className="inline-flex items-center gap-3">
                <Mic size={26} className="shrink-0 text-subtle" />
                The show
              </span>
            }
            className="order-first lg:order-none"
          >
            <div className="mb-5 flex flex-col gap-3">
              {COMMUNITY_SHOW_PARAGRAPHS.map((paragraph) => (
                <p key={paragraph.slice(0, 16)} className="text-subtle text-[13.5px] leading-[1.65]">
                  {paragraph}
                </p>
              ))}
            </div>
            <ShowTopics topics={COMMUNITY_SHOW_TOPICS} />
            <div className="mt-6 pt-6 border-t border-border">
              <CommunityHeading>
                <span className="inline-flex items-center gap-2">
                  <SiPatreon size={17} className="text-subtle" />
                  SUPPORT
                </span>
              </CommunityHeading>
              <div className="mt-4">
                <SupportCard />
              </div>
            </div>
          </SectionPanel>
          <SectionPanel title="The hosts" bodyClassName="flex flex-1 flex-col justify-center">
            {HOSTS.map((host, i) => (
              <div key={host.handle} className={i > 0 ? "border-t border-border pt-6 mt-6 lg:pt-10 lg:mt-10" : undefined}>
                <HostBlock host={host} />
              </div>
            ))}
          </SectionPanel>
        </div>
      </Container>

    </PageShell>
  );
}

function highlightBrand(text: string) {
  return text.split(/(Limited Level-Ups|level up your game)/g).map((part, i) => {
    if (part === "Limited Level-Ups") {
      return (
        <span key={i} className="text-green font-medium">
          {part}
        </span>
      );
    }
    if (part === "level up your game") {
      return (
        <strong key={i} className="text-text font-semibold">
          {part}
        </strong>
      );
    }
    return part;
  });
}

function MemberCount({ members, online }: { members?: number; online?: number }) {
  if (members == null) {
    return null;
  }
  return (
    <div className="font-mono text-[12px] tracking-[0.12em] text-muted flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
      <span>
        <span className="text-text">{members.toLocaleString()}</span> MEMBERS
      </span>
      {online != null ? (
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-green" />
          {online.toLocaleString()} ONLINE NOW
        </span>
      ) : null}
    </div>
  );
}
