import { Link } from "react-router-dom";
import { ArrowRight, Crown } from "lucide-react";
import { SiTwitch, SiYoutube } from "react-icons/si";
import { PageShell } from "../components/PageShell";
import { Container } from "../components/Container";
import { AAvatar, SetGlyph } from "../components/Brand";
import { DiscordIcon } from "../components/BrandIcons";
import { Pips } from "../components/ManaPips";
import { cn } from "../lib/utils";
import { useChampionshipEvents, useChampionshipLinks, usePodCalendar, useSets } from "../data/hooks";
import {
  championshipPodNumber,
  championshipThreadUrl,
  formatChampionshipDay,
  hallOfFameSetHref,
  isChampionshipLive,
} from "../data/setChampionship";
import { SITE_LINKS } from "../data/site";
import { orderedDeckColors, stripDiscriminator } from "../data/utils";
import type { PodChampionshipLinksRow, PodEventSummary, SetSummary } from "../types/leaderboard";

export function HallOfFamePage() {
  const { data: events } = useChampionshipEvents();
  const { data: sets } = useSets();
  const { data: calendar } = usePodCalendar();
  const { data: links } = useChampionshipLinks();

  const linksByEvent = new Map((links ?? []).map((row) => [row.eventId, row]));
  const finished = (events ?? []).filter((event) => event.isFinalized && championshipPodNumber(event.name) === null);
  const liveSets = new Set((events ?? []).filter((event) => isChampionshipLive(event)).map((event) => event.setCode));
  const finishedSets = new Set(finished.map((event) => event.setCode));
  const upcoming = (calendar ?? []).flatMap((day) =>
    day.entries
      .filter((entry) => entry.role === "championship" && !finishedSets.has(entry.glyph))
      .map((entry) => ({ setCode: entry.glyph, day: day.day })),
  );

  return (
    <PageShell subtitle="HALL OF FAME">
      <Container className="py-8 md:py-12 flex flex-col gap-10">
        <h1 className="font-display text-text text-[34px] md:text-[48px] leading-[1.02] tracking-[0.01em]">
          SET CHAMPIONS
        </h1>
        {upcoming.length > 0 ? (
          <section className="flex flex-col gap-4">
            <SectionLabel>UP NEXT</SectionLabel>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {upcoming.map(({ setCode, day }) => (
                <UpcomingCard
                  key={setCode}
                  set={setFor(sets, setCode)}
                  setCode={setCode}
                  day={day}
                  live={liveSets.has(setCode)}
                />
              ))}
            </div>
          </section>
        ) : null}
        <section className="flex flex-col gap-4">
          <SectionLabel>CHAMPIONS</SectionLabel>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {finished.map((event) => (
              <ChampionCard
                key={event.eventId}
                event={event}
                set={setFor(sets, event.setCode)}
                links={linksByEvent.get(event.eventId)}
              />
            ))}
          </div>
        </section>
      </Container>
    </PageShell>
  );
}

function SectionLabel({ children }: { children: string }) {
  return <span className="font-display text-[15px] tracking-[0.14em] text-subtle">{children}</span>;
}

function UpcomingCard({
  set,
  setCode,
  day,
  live,
}: {
  set: SetSummary | undefined;
  setCode: string;
  day: string;
  live: boolean;
}) {
  return (
    <div className="group flex flex-col border border-gold/40 bg-surface transition-colors hover:bg-surface2">
      <Link to={hallOfFameSetHref(setCode)} className="flex items-center gap-4 p-5 no-underline">
        <SetGlyph code={setCode} size={44} className="text-gold" />
        <span className="flex-1 min-w-0 flex flex-col gap-1">
          <span className="font-display text-[22px] tracking-[0.04em] text-text truncate">
            {(set?.name ?? setCode).toUpperCase()}
          </span>
          <span className="text-[14px] text-subtle">{formatChampionshipDay(day)}</span>
        </span>
        <ArrowRight size={18} className="shrink-0 text-subtle transition-transform group-hover:translate-x-0.5" />
      </Link>
      {live ? (
        <span className="flex justify-end border-t border-border">
          <MediaLink icon={<SiTwitch size={15} />} label="TWITCH" url={SITE_LINKS.championshipTwitch} />
        </span>
      ) : null}
    </div>
  );
}

function ChampionCard({
  event,
  set,
  links,
}: {
  event: PodEventSummary;
  set: SetSummary | undefined;
  links: PodChampionshipLinksRow | undefined;
}) {
  return (
    <div className="group flex flex-col border border-border2 bg-surface transition-colors hover:border-gold/60">
      <Link to={hallOfFameSetHref(event.setCode)} className="flex flex-col no-underline">
        <span className="flex items-center gap-3 px-5 py-3 border-b border-border">
          <SetGlyph code={event.setCode} size={24} />
          <span className="flex-1 min-w-0 font-display text-[17px] tracking-[0.06em] text-text truncate">
            {(set?.name ?? event.setCode).toUpperCase()}
          </span>
          <span className="text-[13px] text-subtle shrink-0">{formatChampionshipDay(event.eventDate)}</span>
        </span>
        <span className="flex items-center gap-5 px-5 py-6">
          <span
            className="rounded-full overflow-hidden shrink-0 leading-none"
            style={{ boxShadow: "0 0 0 2px #0a0c10, 0 0 0 3px #ffc63a, 0 0 22px #ffc63a33" }}
          >
            <AAvatar displayName={event.championDisplayName ?? ""} avatarUrl={event.championAvatarUrl} size={72} />
          </span>
          <span className="flex-1 min-w-0 flex flex-col gap-1.5">
            <span className="flex items-center gap-1.5 font-display text-[13px] tracking-[0.14em] text-gold">
              <Crown size={14} />
              CHAMPION
            </span>
            <span className="flex items-center gap-2 min-w-0">
              <span className="font-display text-[26px] tracking-[0.04em] text-text truncate">
                {stripDiscriminator(event.championDisplayName ?? "").toUpperCase()}
              </span>
              {event.championDeckColors ? (
                <Pips colors={orderedDeckColors(event.championDeckColors)} size={15} />
              ) : null}
            </span>
          </span>
        </span>
      </Link>
      <span className="flex items-stretch border-t border-border">
        <Link
          to={hallOfFameSetHref(event.setCode)}
          className="flex-1 flex items-center gap-2 px-5 py-3 no-underline font-display text-[13px] tracking-[0.14em]
            text-subtle transition-colors group-hover:text-green"
        >
          VIEW BRACKET
          <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
        </Link>
        <MediaLink icon={<SiYoutube size={15} />} label="VOD" url={links?.vodUrl ?? null} />
        <MediaLink
          icon={<DiscordIcon size={15} />}
          label="THREAD"
          url={championshipThreadUrl(links?.threadId ?? null)}
        />
      </span>
    </div>
  );
}

function MediaLink({ icon, label, url }: { icon: React.ReactNode; label: string; url: string | null }) {
  const className = "flex items-center gap-1.5 px-4 py-3 border-l border-border font-display text-[13px] tracking-[0.14em]";
  if (!url) {
    return (
      <span title="Not linked yet" className={cn(className, "text-muted cursor-default")}>
        {icon}
        {label}
      </span>
    );
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className={cn(className, "no-underline text-subtle transition-colors hover:text-green")}
    >
      {icon}
      {label}
    </a>
  );
}

function setFor(sets: SetSummary[] | undefined, code: string): SetSummary | undefined {
  return sets?.find((set) => set.code === code);
}
