import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";
import { Link, useLocation } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  BookOpen,
  CalendarRange,
  ChevronDown,
  Flag,
  ListChecks,
  PlayCircle,
  Shuffle,
  Swords,
  Trophy,
} from "lucide-react";
import { GiRoundTable } from "react-icons/gi";
import { PageShell } from "../components/PageShell";
import { DiscordIcon } from "../components/BrandIcons";
import { Container } from "../components/Container";
import { Tooltip } from "../components/Tooltip";
import { SetGlyph, Trophy as TrophyGlyph, fmtPts } from "../components/Brand";
import { compareStandings } from "../components/pod/PodStandings";
import {
  PodStandingRow,
  PodStandingRowSkeleton,
  SeatAvatar,
} from "../components/pod/PodStandingRow";
import { DeckScreenshotModal } from "../components/pod/DeckScreenshotModal";
import {
  useSets,
  usePodEvents,
  usePodEventParticipants,
  usePodDraftArtifact,
  usePodSeasonResults,
} from "../data/hooks";
import { aggregatePodStandings, currentSeason } from "../data/podSeasons";
import { usePodDecklistAccess } from "../data/podDecklistAccess";
import { resolveDeck } from "../data/draft-artifact";
import { playerPath, podDiscordName } from "../data/utils";
import { ACTIVE_SET_CODE, ACTIVE_SET_NAME } from "../data/constants";
import type { PodEventParticipantRow, PodEventSummary, PodLeaderboardRow } from "../types/leaderboard";
import { RailHeader, RailRow } from "../components/Rail";
import {
  DISCHORD_BOT_DM_URL,
  DISCHORD_BOT_NAME,
  POD_DRAFT_CHANNEL_NAME,
  POD_DRAFT_CHANNEL_URL,
  SITE_LINKS,
} from "../data/site";
import { POD_SLOTS, easternHourInLocalTime, nextPodSlotInstant } from "../lib/podSlots";
import { cn } from "../lib/utils";

type SectionDef = { id: string; label: string; tabLabel?: string; icon: LucideIcon; iconClassName?: string };

const SECTIONS: SectionDef[] = [
  { id: "how", label: "How to play", icon: BookOpen },
  { id: "signup", label: "Signing up", icon: ListChecks },
  { id: "draft", label: "Drafting", icon: Shuffle },
  { id: "rounds", label: "Round Pairings", tabLabel: "Pairings", icon: Swords },
  { id: "podium", label: "Podium", icon: Trophy },
  { id: "seasons", label: "Seasons", icon: CalendarRange, iconClassName: "relative -top-[2px]" },
];

const PANEL = "rounded-xl border border-border bg-surface";
const DRAFTMANCER_URL = "https://draftmancer.com";

const WALKTHROUGH_EPISODE_SLUG = "";
const SECTION_BY_ID = new Map(SECTIONS.map((s) => [s.id, s]));

export function PodGuidePage() {
  const [active, setActive] = useState<string>(SECTIONS[0].id);
  const location = useLocation();
  const suppressActive = useRef(false);
  const jumpToken = useRef(0);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (suppressActive.current) {
          return;
        }
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActive(entry.target.id);
          }
        }
      },
      { rootMargin: "-15% 0px -75% 0px" },
    );
    for (const section of SECTIONS) {
      const el = document.getElementById(section.id);
      if (el) {
        observer.observe(el);
      }
    }
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const id = location.hash.slice(1);
    if (!id) {
      return;
    }
    const el = document.getElementById(id);
    if (!el) {
      return;
    }
    const raf = requestAnimationFrame(() => el.scrollIntoView({ block: "start" }));
    return () => cancelAnimationFrame(raf);
  }, [location.hash]);

  const jumpTo = (id: string) => (e: ReactMouseEvent) => {
    e.preventDefault();
    const el = document.getElementById(id);
    if (!el) {
      return;
    }
    setActive(id);
    history.replaceState(null, "", `#${id}`);
    suppressActive.current = true;
    const token = ++jumpToken.current;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    const start = performance.now();
    let lastY = window.scrollY;
    let stable = 0;
    const tick = () => {
      if (jumpToken.current !== token) {
        return;
      }
      const y = window.scrollY;
      stable = Math.abs(y - lastY) >= 1 ? 0 : stable + 1;
      lastY = y;
      const elapsed = performance.now() - start;
      if ((stable > 4 && elapsed > 140) || elapsed > 1600) {
        suppressActive.current = false;
        return;
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };

  return (
    <PageShell subtitle="POD DRAFTS" flushFooter>
      <div className="flex min-h-full flex-1">
        <aside className="hidden lg:block shrink-0 self-stretch w-[clamp(200px,15vw,220px)] border-r border-border bg-surface">
          <div className="sticky top-0 max-h-screen overflow-y-auto overflow-x-hidden">
            <RailLinks active={active} onNavigate={jumpTo} />
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <MobileTabs active={active} onNavigate={jumpTo} />
          <GuideBody />
        </div>
      </div>
    </PageShell>
  );
}

function MobileTabs({
  active,
  onNavigate,
}: {
  active: string;
  onNavigate: (id: string) => (e: ReactMouseEvent) => void;
}) {
  const barRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = barRef.current?.querySelector<HTMLElement>(`[data-tab="${active}"]`);
    el?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [active]);
  return (
    <nav
      aria-label="Guide sections"
      className="lg:hidden sticky top-0 z-10 border-b border-border bg-surface"
    >
      <div ref={barRef} className="flex h-11 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {SECTIONS.map((section) => {
          const Icon = section.icon;
          const on = active === section.id;
          return (
            <a
              key={section.id}
              data-tab={section.id}
              href={`#${section.id}`}
              onClick={onNavigate(section.id)}
              className={cn(
                "relative flex h-full shrink-0 items-center gap-1.5 px-3 font-display text-[15px] tracking-[0.09em] whitespace-nowrap no-underline transition-colors",
                "after:absolute after:inset-x-0 after:-bottom-px after:h-[3px] after:content-['']",
                on ? "text-green after:bg-green" : "text-muted after:bg-transparent hover:text-text",
              )}
            >
              <Icon size={15} strokeWidth={2} className={cn("shrink-0", section.iconClassName)} />
              {section.tabLabel ?? section.label}
            </a>
          );
        })}
      </div>
    </nav>
  );
}

function RailLinks({
  active,
  onNavigate,
}: {
  active: string;
  onNavigate: (id: string) => (e: ReactMouseEvent) => void;
}) {
  return (
    <nav aria-label="On this page">
      <RailHeader icon={GiRoundTable} iconSize={27} label="POD GUIDE" />
      <div>
        {SECTIONS.map((section) => (
          <RailRow
            key={section.id}
            label={section.label}
            icon={section.icon}
            active={active === section.id}
            href={`#${section.id}`}
            onClick={onNavigate(section.id)}
          />
        ))}
      </div>
    </nav>
  );
}

function GuideBody() {
  const early = easternHourInLocalTime(POD_SLOTS[0].easternHour);
  const late = easternHourInLocalTime(POD_SLOTS[1].easternHour);
  return (
    <Container className="py-5 md:py-7">
      <div className="flex flex-col gap-4 md:gap-5">
        <Block id="how" titleOnDesktop={false} watermark maxWidthClass="lg:max-w-[1600px]">
          <div className="grid lg:grid-cols-[4fr_5fr_5fr]">
            <Step
              n={1}
              title="Sign up on Discord"
              href={SITE_LINKS.discordPods}
              icon={<DiscordIcon size={18} className="shrink-0" />}
            >
              <Bullet>
                <BotMention /> posts the daily schedule in <ChannelLink />
              </Bullet>
              <Bullet>
                Choose <B>Early</B> ({early}) or <B>Late</B> ({late})
              </Bullet>
              <Bullet>Pod event thread opens at 6 players</Bullet>
            </Step>
            <Step
              n={2}
              title="Draft on Draftmancer"
              href={DRAFTMANCER_URL}
              hideArrow
              icon={<PlatformIcon src="draftmancer.png" size={24} style={{ filter: OFFWHITE_OUTLINE }} />}
            >
              <Bullet>Link is posted in the Discord thread 10 minutes before start</Bullet>
              <Bullet>
                Set your{" "}
                <Tooltip label="ArenaID#12345">
                  <strong className="cursor-help font-medium text-text">Arena name</strong>
                </Tooltip>{" "}
                in Draftmancer
              </Bullet>
              <Bullet>
                Press <B>Export</B> to copy your decklist into Arena
              </Bullet>
            </Step>
            <Step n={3} title="Play on MTG Arena" icon={<PlatformIcon src="mtga.png" size={20} />}>
              <Bullet>Bot posts pairings at the start of each round</Bullet>
              <Bullet>
                Challenge your opponent to a <B>Limited Tournament Match</B>
              </Bullet>
              <Bullet>Report your result in Discord after each match</Bullet>
            </Step>
          </div>
          <WalkthroughLink />
        </Block>

        <Block id="signup" aside={<LauncherCard />}>
          <Bullets className="mt-2 lg:mt-6">
            <Bullet>Press a Pod Format button to sign up</Bullet>
            <Bullet>
              <B>Early</B> aimed at Europe, <B>Late</B> at America
            </Bullet>
            <Bullet>Pods need at least 6 players to draft</Bullet>
            <Bullet>Notifications are sent when the lobby is ready</Bullet>
            <Bullet>
              Press Leave if you can no longer attend
            </Bullet>
            <Bullet className="hidden lg:flex">Latest set every day, plus Flashbacks and Cube</Bullet>
          </Bullets>
        </Block>

        <Block id="draft" aside={<ReadyCheckCard />}>
          <Bullets className="mt-2 lg:mt-6">
            <Bullet>Ready Check starts when everyone is in Draftmancer</Bullet>
            <Bullet>
              Finish deckbuilding after the draft, then press <B>Export</B>
            </Bullet>
            <Bullet>
              <B>Import</B> your deck on Arena
            </Bullet>
            <Bullet>Craft any cards you don't own</Bullet>
          </Bullets>
        </Block>

        <Block id="rounds" aside={<RoundOneCard />}>
          <Bullets>
            <Bullet>Pods of 6 play Team Draft, 8~10 play Swiss</Bullet>
            <Bullet>If there's more than 10 players, the bot creates separate tables</Bullet>
            <Bullet>Report your match from the thread or your DMs</Bullet>
          </Bullets>
        </Block>

        <Block id="podium" aside={<RecapCard />}>
          <Bullets>
            <Bullet>Post your deck screenshot and submit colors in the thread</Bullet>
            <Bullet>Decks, standings, draft logs and replays are all tracked</Bullet>
          </Bullets>
        </Block>

        <Block id="seasons" aside={<SeasonBoardCard />}>
          <Bullets>
            <Bullet>Latest Set pods run every day of the season</Bullet>
            <Bullet>Flashbacks and Cube are added to the schedule later on</Bullet>
            <Bullet>Every draft counts towards the Leaderboard</Bullet>
            <Bullet>
              Top of the Leaderboard gets a seat at the <B>Set Champion</B> 👑 event, streamed live the weekend before
              the next set's prerelease
            </Bullet>
            <Bullet>
              The top drafter of the season earns the <B>Pod Champion</B> ⚜️ role to wear until the next set
            </Bullet>
          </Bullets>
        </Block>
      </div>
    </Container>
  );
}

type BlockProps = {
  id: string;
  titleOnDesktop?: boolean;
  maxWidthClass?: string;
  watermark?: boolean;
  aside?: ReactNode;
  belowAside?: ReactNode;
  children: ReactNode;
};

function Block({ id, titleOnDesktop = true, maxWidthClass, watermark, aside, belowAside, children }: BlockProps) {
  const section = SECTION_BY_ID.get(id) ?? SECTIONS[0];
  const Icon = section.icon;
  const maxW = maxWidthClass ?? (aside ? "lg:max-w-[1260px]" : "lg:max-w-[820px]");
  const heading = (
    <h2
      className={cn(
        "relative items-center gap-3 font-display text-text text-[22px] md:text-[26px] xl:text-[30px] leading-[0.95] tracking-[0.03em] mb-5",
        titleOnDesktop ? "flex" : "hidden",
      )}
    >
      <Icon size={26} strokeWidth={2} className={cn("-ml-[3px] shrink-0 text-green", section.iconClassName)} />
      {section.label}
    </h2>
  );
  return (
    <section id={id} className={cn(PANEL, "group relative scroll-mt-[52px] lg:scroll-mt-4 overflow-hidden p-5 md:p-6", maxW)}>
      {watermark ? (
        <Icon
          size={96}
          strokeWidth={1.25}
          className="pointer-events-none absolute right-4 top-3 hidden md:block text-border2/40 opacity-30 transition-[opacity,color] duration-300 group-hover:opacity-100 group-hover:text-green/[0.14]"
        />
      ) : null}
      {aside ? (
        <>
          <div className="relative flex flex-col gap-5 min-[1180px]:flex-row min-[1180px]:items-start min-[1180px]:gap-6 min-[1520px]:gap-8">
            <div className="w-full max-w-[720px] min-w-0 min-[1180px]:max-w-none min-[1180px]:flex-1 min-[1520px]:flex-none min-[1520px]:w-[580px] min-[1520px]:shrink-0">
              {heading}
              {children}
            </div>
            <div className="w-full max-w-[600px] min-[1180px]:w-[500px] min-[1180px]:max-w-none min-[1180px]:shrink-0 min-[1520px]:w-[600px]">
              {aside}
            </div>
          </div>
          {belowAside ? <div className="relative">{belowAside}</div> : null}
        </>
      ) : (
        <>
          {heading}
          <div className="relative">{children}</div>
        </>
      )}
    </section>
  );
}


function Bullets({ children, className }: { children: ReactNode; className?: string }) {
  return <ul className={cn("flex flex-col gap-2.5 pl-1", className)}>{children}</ul>;
}

function Bullet({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <li className={cn("flex gap-3 text-subtle text-[14px] md:text-[15px] xl:text-[16px] leading-[1.55]", className)}>
      <span className="flex h-[1.55em] w-3 shrink-0 items-center justify-center">
        <span className="h-[5px] w-[5px] rotate-45 bg-green" />
      </span>
      <span className="flex-1">{children}</span>
    </li>
  );
}

type StepProps = {
  n: number;
  title: string;
  href?: string;
  hideArrow?: boolean;
  icon: ReactNode;
  children: ReactNode;
};

const STEP_TITLE ="inline-flex flex-wrap items-center gap-x-2 gap-y-1 font-display text-text text-[19px] md:text-[21px] tracking-[0.04em] leading-none";

function Step({ n, title, href, hideArrow, icon, children }: StepProps) {
  const heading = href ? (
    <a href={href} target="_blank" rel="noreferrer" className={cn(STEP_TITLE, "no-underline transition-colors hover:text-green")}>
      {title}
      {icon}
      {hideArrow ? null : <ArrowRight size={16} strokeWidth={2} className="shrink-0" />}
    </a>
  ) : (
    <span className={STEP_TITLE}>
      {title}
      {icon}
    </span>
  );
  return (
    <div className="flex min-w-0 flex-col gap-3 border-border py-2.5 first:pt-0 last:pb-0 [&:not(:first-child)]:border-t lg:px-6 lg:py-0 lg:first:pl-0 lg:last:pr-0 lg:[&:not(:first-child)]:border-l lg:[&:not(:first-child)]:border-t-0">
      <div className="flex items-center gap-3 pl-[3.5px]">
        <span className="font-display text-green text-[28px] leading-none">{n}</span>
        {heading}
      </div>
      <ul className="flex flex-col gap-2 pl-[3.5px]">{children}</ul>
    </div>
  );
}

const OFFWHITE_OUTLINE =
  "drop-shadow(0.5px 0 0 #f0f0f0) drop-shadow(-0.5px 0 0 #f0f0f0) drop-shadow(0 0.5px 0 #f0f0f0) drop-shadow(0 -0.5px 0 #f0f0f0)";

function PlatformIcon({ src, size, style }: { src: string; size: number; style?: CSSProperties }) {
  return (
    <img src={`${import.meta.env.BASE_URL}platforms/${src}`} alt="" width={size} height={size} className="shrink-0" style={style} />
  );
}

const DISCORD_FONT = "'gg sans', 'Noto Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif";
const DISCORD_BUTTON_GREEN = "#248046";
const EMBED_ACCENT = "#2ecc71";
const TIMESTAMP_BG = "rgba(114,118,125,0.3)";

const LAUNCHER_SLOTS = [
  { short: "Early", label: "Early Pod", emoji: "💫", color: "#5CA8E0", pillBg: "rgba(92,168,224,0.16)",
    roster: ["Nassif", "Finkel", "LSV", "JED"] },
  { short: "Late", label: "Late Pod", emoji: "☄️", color: "#9B8AE6", pillBg: "rgba(155,138,230,0.16)",
    roster: ["Paolo", "Shota", "Reid", "Chapin"] },
] as const;

const TITLE_DAY_FMT = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const FULL_DATE_FMT = new Intl.DateTimeFormat(undefined, {
  weekday: "long", month: "short", day: "numeric",
});
const SHORT_DATE_FMT = new Intl.DateTimeFormat(undefined, {
  weekday: "short", month: "short", day: "numeric",
});
const CLOCK_FMT = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

function LauncherCard() {
  const setName = ACTIVE_SET_NAME;
  const code = ACTIVE_SET_CODE;
  const glyphCode = ACTIVE_SET_CODE;
  const slots = LAUNCHER_SLOTS.map((slot, index) => ({
    ...slot, when: nextPodSlotInstant(POD_SLOTS[index].easternHour),
  }));
  return (
    <div style={{ fontFamily: DISCORD_FONT }}>
      <div className="overflow-hidden rounded-md bg-[#2b2d31]" style={{ borderLeft: `4px solid ${EMBED_ACCENT}` }}>
        <div className="p-4">
          <div className="flex items-center gap-2 text-white font-bold text-[17px]">
            <span aria-hidden>🚀</span>
            <span>Daily Pod Launcher - {TITLE_DAY_FMT.format(slots[0].when)}</span>
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 text-[#dbdee1] text-[14px]">
            <span className="font-semibold">Choose a time to draft</span>
            <SetGlyph code={glyphCode} size={16} className="text-white" />
            <span className="font-semibold text-white">{setName}</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
            {slots.map((slot) => (
              <div key={slot.short} className="min-w-0">
                <div className="inline-flex items-center gap-1 text-[14px] font-medium">
                  <span aria-hidden>{slot.emoji}</span>
                  <span className="rounded px-1" style={{ backgroundColor: slot.pillBg, color: slot.color }}>
                    @{slot.label}
                  </span>
                </div>
                <div className="mt-1">
                  <span className="rounded-sm px-1 text-[#dbdee1] text-[13px]" style={{ backgroundColor: TIMESTAMP_BG }}>
                    <span className="sm:hidden">{SHORT_DATE_FMT.format(slot.when)}</span>
                    <span className="hidden sm:inline">{FULL_DATE_FMT.format(slot.when)}</span>
                    {" at "}{CLOCK_FMT.format(slot.when)}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center gap-1 text-[#f2f3f5] text-[14px] font-semibold">
                  <SetGlyph code={glyphCode} size={20} className="text-white" />
                  <span>{slot.short} {code} ({slot.roster.length})</span>
                </div>
                <div className="mt-1 ml-1.5 flex gap-2">
                  <span className="w-1 shrink-0 self-stretch rounded-full bg-[#4e5058]" />
                  <div className="text-[#dbdee1] text-[14px] leading-[1.45]">
                    {slot.roster.map((name) => <div key={name}>{name}</div>)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-2 flex items-center gap-1.5 sm:gap-2">
        {slots.map((slot) => (
          <span
            key={slot.short}
            className="inline-flex items-center gap-1 rounded-lg px-2.5 sm:px-4 py-2 text-white text-[14px] font-semibold"
            style={{ backgroundColor: DISCORD_BUTTON_GREEN }}
          >
            <SetGlyph code={glyphCode} size={19} className="text-white" />
            {slot.short} {code}
          </span>
        ))}
        <span
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg px-2.5 sm:px-4 py-2 text-white text-[14px]"
          style={{ backgroundColor: SECONDARY_GREY }}
        >
          <span aria-hidden>❌</span> Leave
        </span>
      </div>
    </div>
  );
}

const SECONDARY_GREY = "#4e5058";

type ReadyRow = { name: string; handle: string; ready?: boolean };

const READY_ROSTER: ReadyRow[] = [
  { name: "Finkel", handle: "JonnyMagic#40129", ready: true },
  { name: "Nassif", handle: "yellowhat#61023", ready: true },
  { name: "Reid", handle: "reiderrabit#75540", ready: true },
  { name: "JED", handle: "JiRock#31337", ready: true },
  { name: "Paolo", handle: "PVDDR#00777" },
  { name: "Shota", handle: "yaya3" },
  { name: "LSV", handle: "LSV#00420" },
  { name: "Chapin", handle: "Chapin#13000" },
];

const READY_DATE_FMT = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });

function tomorrow(): Date {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  return date;
}

function ReadyRosterGroup(
  { marker, label, rows, showHandles = true }:
  { marker: string; label: string; rows: ReadyRow[]; showHandles?: boolean },
) {
  return (
    <div>
      <div className="flex items-center gap-1.5 whitespace-nowrap text-white text-[15px] font-semibold">
        <span aria-hidden>{marker}</span>{label} ({rows.length})
      </div>
      <div className="mt-1 ml-1.5 flex gap-2">
        <span className="w-1 shrink-0 self-stretch rounded-full" style={{ backgroundColor: SECONDARY_GREY }} />
        {showHandles ? (
          <div className="grid grid-cols-[auto_auto] items-center gap-x-2.5 gap-y-1">
            {rows.map((row) => (
              <Fragment key={row.name}>
                <span className="text-[#dbdee1] text-[14px]">{row.name}</span>
                <span
                  className="mono justify-self-start rounded border px-1.5 text-[12px]"
                  style={{ backgroundColor: "#2d2f33", borderColor: "#4e5058", color: "#b5bac1" }}
                >
                  {row.handle}
                </span>
              </Fragment>
            ))}
          </div>
        ) : (
          <div className="flex flex-col gap-1 text-[#dbdee1] text-[14px]">
            {rows.map((row) => <span key={row.name}>{row.name}</span>)}
          </div>
        )}
      </div>
    </div>
  );
}

function ReadyCheckCard() {
  const code = ACTIVE_SET_CODE;
  const glyphCode = ACTIVE_SET_CODE;
  const ready = READY_ROSTER.filter((row) => row.ready);
  const pending = READY_ROSTER.filter((row) => !row.ready);
  return (
    <div style={{ fontFamily: DISCORD_FONT }}>
      <div className="overflow-hidden rounded-md bg-[#2b2d31]" style={{ borderLeft: `4px solid ${EMBED_ACCENT}` }}>
        <div className="p-4">
          <div className="flex items-center gap-1.5 text-white font-bold text-[17px]">
            <SetGlyph code={glyphCode} size={20} className="text-white" />
            <span>{code} {READY_DATE_FMT.format(tomorrow())} Early Pod</span>
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 text-white font-semibold text-[15px]">
            <span aria-hidden>🔔</span>
            <span>Ready Check initiated</span>
          </div>
          <div className="mt-3 flex justify-between lg:grid lg:grid-cols-2 lg:gap-x-4">
            <ReadyRosterGroup marker="✅" label="Ready" rows={ready} />
            <ReadyRosterGroup marker="⏳" label="Pending" rows={pending} showHandles={false} />
          </div>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-[14px] text-white">
        <span className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 font-semibold" style={{ backgroundColor: DISCORD_BUTTON_GREEN }}>
          <span className="text-[17px] leading-none">✅</span> I&apos;m Ready
        </span>
      </div>
    </div>
  );
}

const ROUND1_PAIRINGS = [
  { a: "PlayerName", b: "Paolo" },
  { a: "Finkel", b: "Shota" },
  { a: "LSV", b: "Reid" },
  { a: "JED", b: "Chapin" },
];

function MonoPill({ children }: { children: ReactNode }) {
  return (
    <span
      className="mono rounded border px-1.5 text-[12px]"
      style={{ backgroundColor: "#2d2f33", borderColor: "#4e5058", color: "#b5bac1" }}
    >
      {children}
    </span>
  );
}

function RoundOneCard() {
  return (
    <div style={{ fontFamily: DISCORD_FONT }}>
      <div className="overflow-hidden rounded-md bg-[#2b2d31]" style={{ borderLeft: `4px solid ${EMBED_ACCENT}` }}>
        <div className="p-4">
          <div className="flex items-center gap-1.5 text-white font-bold text-[17px]">
            <span aria-hidden>⚔️</span>
            <span>Round 1 Pairings</span>
            <span aria-hidden>⚔️</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
            {ROUND1_PAIRINGS.map((pair) => (
              <div key={pair.a} className="flex flex-wrap items-center gap-1.5 text-[14px] text-[#dbdee1]">
                <span aria-hidden>⚔️</span>
                <span className={cn(pair.a === "PlayerName" && "italic")}>{pair.a}</span>
                <span className="text-[#949ba4]">vs</span>
                <span>{pair.b}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 flex gap-1.5 text-[14px] text-[#dbdee1]">
            <span aria-hidden>🎯</span>
            <span>Opponent DM'd. Use <MonoPill>/report-results</MonoPill> or the menu below after your match</span>
          </div>
        </div>
      </div>
      <div className="mt-2 flex w-fit items-center gap-8 rounded border border-[#232428] bg-[#1e1f22] px-3 py-2 text-[14px] text-[#dbdee1]">
        <span>⚔️ <span className="italic">PlayerName</span> vs Paolo</span>
        <ChevronDown size={18} className="text-[#949ba4]" />
      </div>
    </div>
  );
}

const ASIDE_FOOT =
  "mt-3 inline-flex items-center gap-1.5 font-display text-[13px] tracking-[0.04em] text-green no-underline hover:underline";

const RECAP_TOP_PLACEMENTS = 4;
const RECAP_COLS = "[grid-template-columns:16px_1fr_46px_32px_34px] " +
  "lg:[grid-template-columns:22px_1fr_80px_70px_86px]";
const RECAP_PAD = "pl-2 pr-1.5 lg:pr-2";

function mainColorsOnly(colors: string | null): string | null {
  return colors ? colors.replace(/[a-z]/g, "") : colors;
}

function latestEightPlayerPod(events: PodEventSummary[] | undefined): PodEventSummary | undefined {
  let latest: PodEventSummary | undefined;
  let fallback: PodEventSummary | undefined;
  for (const event of events ?? []) {
    if (!event.isFinalized || event.isTeamDraft) {
      continue;
    }
    if (!fallback || event.eventDate > fallback.eventDate) {
      fallback = event;
    }
    if (event.participantCount !== 8) {
      continue;
    }
    if (!latest || event.eventDate > latest.eventDate) {
      latest = event;
    }
  }
  return latest ?? fallback;
}

function RecapCard() {
  const { data: events } = usePodEvents(ACTIVE_SET_CODE);
  const pod = latestEightPlayerPod(events);
  const { data: participants } = usePodEventParticipants(pod?.eventId);
  const { data: draftArtifact } = usePodDraftArtifact(pod?.eventId);
  const decklistAccess = usePodDecklistAccess(pod);
  const [deckTarget, setDeckTarget] = useState<PodEventParticipantRow | null>(null);
  const ranked = useMemo(
    () => (participants ? [...participants].sort(compareStandings).slice(0, RECAP_TOP_PLACEMENTS) : undefined),
    [participants],
  );
  const deckTargetMainboard = useMemo(
    () => (draftArtifact && deckTarget?.seatIndex != null ? resolveDeck(draftArtifact, deckTarget.seatIndex) : null),
    [draftArtifact, deckTarget],
  );
  const cycleDeck = (direction: number) => {
    const list = ranked ?? [];
    if (!deckTarget || list.length === 0) {
      return;
    }
    const index = list.indexOf(deckTarget);
    if (index === -1) {
      return;
    }
    for (let step = 1; step <= list.length; step++) {
      const next = list[(((index + direction * step) % list.length) + list.length) % list.length];
      if (decklistAccess.canViewSeat(next.avatarUrl)) {
        setDeckTarget(next);
        return;
      }
    }
  };
  if (!pod) {
    return (
      <Link to="/pods" className={ASIDE_FOOT}>
        <Flag size={14} strokeWidth={2} className="shrink-0" />
        Open the pod board
        <ArrowRight size={14} strokeWidth={2} className="shrink-0" />
      </Link>
    );
  }
  return (
    <>
      <div className="overflow-hidden border border-border bg-surface">
        <div
          className={cn(
            "grid items-center gap-x-2 lg:gap-x-3 border-b border-border bg-surface2",
            RECAP_PAD, RECAP_COLS,
          )}
          style={{ height: 34 }}
        >
          <div className="col-span-2 flex items-center gap-2 min-w-0">
            <SetGlyph code={pod.setCode} size={17} className="shrink-0 text-white" />
            <span className="truncate font-display tracking-[0.04em] text-white text-[15px] min-w-0">{pod.name}</span>
          </div>
          <span className="font-display text-muted tracking-[0.16em] text-[11px] whitespace-nowrap">
            <span className="hidden min-[1180px]:inline">COLORS</span>
          </span>
          <span className="font-display text-muted tracking-[0.16em] text-[11px] text-center whitespace-nowrap">
            <span className="hidden min-[1180px]:inline">RESULT</span>
          </span>
          <Link to={`/pods/${pod.slug}`} className="inline-flex items-center justify-end gap-1 font-display tracking-[0.05em] text-[13px] text-white no-underline hover:underline">
            RECAP
            <ArrowRight size={14} strokeWidth={2} className="shrink-0" />
          </Link>
        </div>
        <div className="flex flex-col gap-[1px] bg-bg pb-[1px]">
          {ranked
            ? ranked.map((p, index) => {
                const rank = p.placement ?? index + 1;
                return (
                  <PodStandingRow
                    key={`${p.eventId}-${p.displayName}`}
                    p={{ ...p, deckColors: mainColorsOnly(p.deckColors) }}
                    rank={rank}
                    trophy={rank === 1}
                    dense
                    iconOnly
                    cols={RECAP_COLS}
                    padX={RECAP_PAD}
                    onShowDeck={() => setDeckTarget(p)}
                  />
                );
              })
            : Array.from({ length: RECAP_TOP_PLACEMENTS }).map((_, i) => (
                <PodStandingRowSkeleton key={i} cols={RECAP_COLS} />
              ))}
        </div>
      </div>
      {deckTarget && (
        <DeckScreenshotModal
          participant={{
            eventId: deckTarget.eventId,
            displayName: podDiscordName(deckTarget),
            participantDisplayName: deckTarget.displayName,
            deckColors: deckTarget.deckColors,
            deckScreenshotUrl: deckTarget.deckScreenshotUrl,
            deckScreenshotCaption: deckTarget.deckScreenshotCaption,
            mainboard: deckTargetMainboard,
            record: deckTarget.record,
          }}
          draftLogHref={
            draftArtifact && decklistAccess.canViewSeat(deckTarget.avatarUrl)
              ? `/pods/${pod.slug}/${deckTarget.playerSlug ?? deckTarget.seatIndex}`
              : null
          }
          breakdownHref={`/pods/${pod.slug}?player=${encodeURIComponent(podDiscordName(deckTarget))}`}
          onClose={() => setDeckTarget(null)}
          onPrev={() => cycleDeck(-1)}
          onNext={() => cycleDeck(1)}
        />
      )}
    </>
  );
}

const SEASON_BOARD_TOP_N = 6;
const SEASON_COLS = "grid items-center gap-x-2 lg:gap-x-3 [grid-template-columns:16px_1fr_58px_56px] " +
  "lg:[grid-template-columns:22px_1fr_72px_66px]";
const GUIDE_TABLE_PAD = "pl-2 pr-3 lg:pr-4";
const SEASON_METRIC_HEAD = "font-display text-[11px] tracking-[0.2em] text-muted text-center whitespace-nowrap";
const SEASON_METRIC = "font-display text-[16px] tabular-nums text-text text-center";

function SeasonRow({ row }: { row: PodLeaderboardRow }) {
  return (
    <div className={cn(SEASON_COLS, "bg-surface py-1.5", GUIDE_TABLE_PAD)}>
      <span className="mono text-center tabular-nums text-muted text-[14px]">{row.rank}</span>
      <Link
        to={playerPath(row.slug, ACTIVE_SET_CODE)}
        className="flex items-center gap-2 lg:gap-2.5 min-w-0 justify-self-start w-fit max-w-full no-underline text-text transition-colors hover:text-green"
      >
        <SeatAvatar name={row.displayName} avatarUrl={row.avatarUrl} size={28} teamSide={null} />
        <span className="font-display leading-none tracking-[0.04em] text-[16px] truncate">
          {row.displayName.toUpperCase()}
        </span>
      </Link>
      <span className={cn(SEASON_METRIC, "flex items-center justify-center gap-1")}>
        <TrophyGlyph size={14} color="#ffc63a" />
        {row.trophies}
      </span>
      <span className={SEASON_METRIC}>{fmtPts(row.points ?? 0)}</span>
    </div>
  );
}

function SeasonBoardCard() {
  const { data: sets } = useSets();
  const season = currentSeason(sets);
  const { data: results } = usePodSeasonResults(season);
  const top = aggregatePodStandings(results)?.slice(0, SEASON_BOARD_TOP_N);
  const loading = results === undefined;
  return (
    <div className="overflow-hidden border border-border bg-surface">
      <div className={cn(SEASON_COLS, "border-b border-border bg-surface2", GUIDE_TABLE_PAD)} style={{ height: 34 }}>
        <Link
          to="/pods"
          className="col-span-2 flex items-center gap-2 min-w-0 no-underline text-white hover:underline"
        >
          <SetGlyph code={ACTIVE_SET_CODE} size={17} className="shrink-0 text-white" />
          <span className="font-display tracking-[0.04em] text-[15px]">SEASON LEADERBOARD</span>
          <ArrowRight size={14} strokeWidth={2} className="shrink-0" />
        </Link>
        <span className={SEASON_METRIC_HEAD}>TROPHIES</span>
        <span className={SEASON_METRIC_HEAD}>POINTS</span>
      </div>
      <div className="flex flex-col gap-[1px] bg-bg pb-[1px]">
        {loading
          ? Array.from({ length: SEASON_BOARD_TOP_N }).map((_, i) => (
              <div key={i} className={cn(SEASON_COLS, "bg-surface py-1.5", GUIDE_TABLE_PAD)}>
                <span className="h-3 w-3 bg-surface2 animate-pulse mx-auto" />
                <div className="flex items-center gap-2 lg:gap-2.5">
                  <div className="h-[28px] w-[28px] bg-surface2 shrink-0" />
                  <div className="h-3.5 w-28 bg-surface2 animate-pulse" />
                </div>
                <div className="h-3.5 w-8 bg-surface2 animate-pulse justify-self-end" />
                <div className="h-3.5 w-8 bg-surface2 animate-pulse justify-self-end" />
              </div>
            ))
          : (top ?? []).map((row) => <SeasonRow key={row.slug} row={row} />)}
      </div>
    </div>
  );
}

function WalkthroughLink() {
  if (!WALKTHROUGH_EPISODE_SLUG) {
    return null;
  }
  return (
    <Link
      to={`/episodes/${WALKTHROUGH_EPISODE_SLUG}`}
      className="mt-6 inline-flex items-center gap-2.5 rounded-lg border border-green/30 bg-green/10 px-4 py-2.5 font-display text-[14px] tracking-[0.04em] text-green no-underline transition-colors hover:bg-green/20"
    >
      <PlayCircle size={18} strokeWidth={2} className="shrink-0" />
      Watch the walkthrough
      <ArrowRight size={15} strokeWidth={2} className="shrink-0" />
    </Link>
  );
}

function B({ children }: { children: ReactNode }) {
  return <strong className="font-medium text-text">{children}</strong>;
}

function BotMention() {
  return (
    <a
      href={DISCHORD_BOT_DM_URL}
      target="_blank"
      rel="noreferrer"
      className="relative -top-px inline-flex items-center gap-1 whitespace-nowrap align-middle font-medium text-green no-underline hover:underline"
    >
      <img
        src={`${import.meta.env.BASE_URL}llu-bot-avatar-transparent.png`}
        alt=""
        className="relative -top-[3px] h-[22px] w-[22px] -my-1"
      />
      {DISCHORD_BOT_NAME}
    </a>
  );
}

function ChannelLink() {
  return (
    <a
      href={POD_DRAFT_CHANNEL_URL}
      target="_blank"
      rel="noreferrer"
      className="whitespace-nowrap font-medium text-text no-underline transition-colors hover:text-green"
    >
      {POD_DRAFT_CHANNEL_NAME}
    </a>
  );
}


