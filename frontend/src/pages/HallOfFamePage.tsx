import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ArrowUpRight, Crown, HelpCircle } from "lucide-react";
import { SiTwitch, SiYoutube } from "react-icons/si";
import { PageShell } from "../components/PageShell";
import { Container } from "../components/Container";
import { AAvatar, SetGlyph } from "../components/Brand";
import { DiscordIcon } from "../components/BrandIcons";
import { RoleMention } from "../components/RoleMention";
import { Tooltip } from "../components/Tooltip";
import { cn } from "../lib/utils";
import { useChampionshipEvents, useChampionshipLinks, usePodCalendar, useSets } from "../data/hooks";
import {
  championshipPodNumber,
  championshipThreadUrl,
  championshipViewHref,
  formatChampionshipDay,
  hallOfFameSetHref,
  isChampionshipLive,
} from "../data/setChampionship";
import { SITE_LINKS } from "../data/site";
import { stripDiscriminator } from "../data/utils";
import type { PodChampionshipLinksRow, PodEventSummary, SetSummary } from "../types/leaderboard";

export function HallOfFamePage() {
  const { data: events } = useChampionshipEvents();
  const { data: sets } = useSets();
  const { data: calendar } = usePodCalendar();
  const { data: links } = useChampionshipLinks();

  const linksByEvent = new Map((links ?? []).map((row) => [row.eventId, row]));
  const championships = (events ?? []).filter((event) => championshipPodNumber(event.name) === null);
  const finished = championships.filter((event) => event.isFinalized);
  const finishedSets = new Set(finished.map((event) => event.setCode));
  const upcoming = (calendar ?? []).flatMap((day) =>
    day.entries
      .filter((entry) => entry.role === "championship" && !finishedSets.has(entry.glyph))
      .map((entry) => ({ setCode: entry.glyph, day: day.day })),
  );
  const liveEventFor = (setCode: string) =>
    championships.find((event) => event.setCode === setCode && isChampionshipLive(event));

  return (
    <PageShell subtitle="HALL OF FAME">
      <Container className="py-8 md:py-12 flex flex-col gap-10">
        <span className="flex items-center gap-3">
          <h1 className="font-display text-text text-[34px] md:text-[48px] leading-[1.02] tracking-[0.01em]">
            SET CHAMPIONS
          </h1>
          <ChampionshipInfoButton />
        </span>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {upcoming.map(({ setCode, day }) => {
            const liveEvent = liveEventFor(setCode);
            return (
              <ChampionshipCard
                key={setCode}
                setCode={setCode}
                set={setFor(sets, setCode)}
                day={day}
                champion={null}
                live={liveEvent !== undefined}
                links={liveEvent ? linksByEvent.get(liveEvent.eventId) : undefined}
              />
            );
          })}
          {finished.map((event) => (
            <ChampionshipCard
              key={event.eventId}
              setCode={event.setCode}
              set={setFor(sets, event.setCode)}
              day={event.eventDate}
              champion={event}
              live={false}
              links={linksByEvent.get(event.eventId)}
            />
          ))}
        </div>
      </Container>
    </PageShell>
  );
}

function ChampionshipInfoButton() {
  const [open, setOpen] = useState(false);
  const explainer = (
    <span className="flex flex-col gap-2 max-w-[320px] p-1.5 text-[14px] leading-snug">
      <span className="font-display text-[15px] tracking-[0.14em] text-gold">👑 SET CHAMPIONSHIP</span>
      <span>
        Each set we host a tournament where top performing Discord members draft for the privilege of being crowned{" "}
        <RoleMention role="Set Champion" />
      </span>
      <span>Leaderboard standings decide who plays</span>
      <span>8-player Pod Draft, Best-of-Three, 3 Swiss rounds paired by record</span>
      <span>
        Matches streamed at{" "}
        <a
          href={SITE_LINKS.championshipTwitch}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 no-underline text-green transition-colors hover:text-green/70"
        >
          twitch.tv/GatoDelFuego
          <ArrowUpRight size={14} className="shrink-0" />
        </a>
      </span>
    </span>
  );
  return (
    <Tooltip
      label={explainer}
      side="bottom"
      align="start"
      open={open}
      onOpenChange={setOpen}
      interactive
      hideArrow
    >
      <button
        type="button"
        aria-label="About the Set Championship"
        onClick={() => setOpen((current) => !current)}
        className="flex items-center border-0 bg-transparent p-0 cursor-pointer text-muted transition-colors
          hover:text-green"
      >
        <HelpCircle size={22} strokeWidth={2} />
      </button>
    </Tooltip>
  );
}

function ChampionshipCard({
  setCode,
  set,
  day,
  champion,
  live,
  links,
}: {
  setCode: string;
  set: SetSummary | undefined;
  day: string;
  champion: PodEventSummary | null;
  live: boolean;
  links: PodChampionshipLinksRow | undefined;
}) {
  const upcoming = champion === null;
  const href = upcoming && !live ? championshipViewHref(setCode, "top8") : hallOfFameSetHref(setCode);
  const media = upcoming
    ? { icon: <SiTwitch size={15} />, label: "TWITCH", url: live ? SITE_LINKS.championshipTwitch : null }
    : { icon: <SiYoutube size={15} />, label: "VOD", url: links?.vodUrl ?? null };
  const eventUrl = championshipThreadUrl(links?.threadId ?? null);
  return (
    <div
      className={cn(
        "group flex flex-col border bg-surface transition-colors",
        upcoming ? "border-gold/50 hover:border-gold" : "border-border2 hover:border-green",
      )}
    >
      <Link to={href} className="flex flex-col no-underline">
        <span className="flex items-center gap-3 px-5 py-3 border-b border-border">
          <SetGlyph code={setCode} size={24} />
          <span className="flex-1 min-w-0 font-display text-[17px] tracking-[0.06em] text-text truncate">
            {(set?.name ?? setCode).toUpperCase()}
          </span>
          <span className="flex items-center gap-x-3 shrink-0">
            {upcoming ? (
              <span className="font-display text-[13px] tracking-[0.14em] text-gold">
                {live ? "LIVE NOW" : "UP NEXT"}
              </span>
            ) : null}
            <span className="text-[13px] text-subtle">{formatChampionshipDay(day)}</span>
          </span>
        </span>
        <span className="flex items-center gap-5 px-5 py-6">
          <span
            className="rounded-full overflow-hidden shrink-0 leading-none bg-surface2 flex items-center justify-center"
            style={{ width: 72, height: 72, boxShadow: "0 0 0 2px #0a0c10, 0 0 0 3px #ffc63a, 0 0 22px #ffc63a33" }}
          >
            {champion ? (
              <AAvatar
                displayName={champion.championDisplayName ?? ""}
                avatarUrl={champion.championAvatarUrl}
                size={72}
              />
            ) : (
              <SetGlyph code={setCode} size={40} className="text-gold" />
            )}
          </span>
          <span className="relative flex-1 min-w-0">
            <span
              className="absolute bottom-full mb-1.5 flex items-center gap-1.5 font-display text-[13px]
                tracking-[0.14em] text-gold"
            >
              <Crown size={14} />
              {setCode} CHAMPION
            </span>
            <span className="block font-display text-[34px] leading-none tracking-[0.04em] text-text truncate">
              {champion ? stripDiscriminator(champion.championDisplayName ?? "").toUpperCase() : "TBD"}
            </span>
          </span>
        </span>
      </Link>
      <span className="flex items-stretch border-t border-border">
        <Link
          to={href}
          className={cn(
            "flex-1 flex items-center gap-2 px-5 py-3 no-underline font-display text-[13px] tracking-[0.14em]",
            "text-subtle transition-colors",
            upcoming ? "group-hover:text-gold" : "group-hover:text-green",
          )}
        >
          TOP 8
          <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
        </Link>
        <MediaLink icon={media.icon} label={media.label} url={media.url} />
        <MediaLink icon={<DiscordIcon size={15} />} label="EVENT" url={eventUrl} />
      </span>
    </div>
  );
}

function MediaLink({ icon, label, url }: { icon: React.ReactNode; label: string; url: string | null }) {
  if (!url) {
    return null;
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-1.5 px-4 py-3 border-l border-border font-display text-[13px] tracking-[0.14em]
        no-underline text-subtle transition-colors hover:text-green"
    >
      {icon}
      {label}
    </a>
  );
}

function setFor(sets: SetSummary[] | undefined, code: string): SetSummary | undefined {
  return sets?.find((set) => set.code === code);
}
