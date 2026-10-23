import { useMemo, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { BackButton, MobilePageHeader } from "../components/PageNav";
import { GrandFinal } from "../components/hallOfFame/ChampionshipBracket";
import {
  championshipMedia,
  ChampionshipMobileTitle,
  ChampionshipTabs,
  ChampionshipTitle,
  UPCOMING_TABS,
  type ChampionshipMedia,
  type ChampionshipTab,
} from "../components/hallOfFame/ChampionshipChrome";
import { PlayerProfileCard } from "../components/hallOfFame/PlayerProfileCard";
import { QualificationList } from "../components/hallOfFame/QualificationList";
import { useChampionshipEvent, useChampionshipPlayers } from "../components/hallOfFame/useChampionship";
import { useChampionshipField } from "../components/hallOfFame/useChampionshipField";
import { useChampionshipLinks, usePodCalendar, usePodEventMatches, usePodEventParticipants } from "../data/hooks";
import { useIsMobile } from "../lib/use-is-mobile";
import { cn } from "../lib/utils";
import { playerPath, podEventTitle } from "../data/utils";
import {
  championshipPodNumber,
  championshipViewFromSegment,
  championshipViewHref,
  HALL_OF_FAME_PATH,
  hallOfFameSetHref,
  isChampionshipLive,
  isPodView,
  participantByName,
  podView,
  type ChampionshipView,
} from "../data/setChampionship";
import type { PodEventSummary } from "../types/leaderboard";
import { PodPage } from "./PodPage";

const UPCOMING_LABEL = "👑 SET CHAMPIONSHIP";

export function HallOfFameSetPage() {
  const params = useParams();
  const setCode = (params.setCode ?? "").toUpperCase();
  const view = championshipViewFromSegment(params.view);
  const { event, pods, isLoading } = useChampionshipEvent(setCode);
  const toBase = <Navigate to={hallOfFameSetHref(setCode)} replace />;
  if (!view) {
    return toBase;
  }
  const started = event !== undefined && (event.isFinalized || new Date(event.eventTime).getTime() <= Date.now());
  if (event && started && pods.length > 0) {
    const tabs = splitChampionshipTabs(pods);
    if (view === "table") {
      return <GrandFinalPage event={event} tabs={tabs} />;
    }
    const pod = pods.find((entry) => podView(championshipPodNumber(entry.name) ?? 0) === view);
    return pod ? <PodPage slugOverride={pod.slug} championshipView={view} championshipTabs={tabs} /> : toBase;
  }
  if (event && started) {
    return isPodView(view) ? toBase : <PodPage slugOverride={event.slug} championshipView={view} />;
  }
  if (isLoading) {
    return null;
  }
  if (view === "bracket" || isPodView(view)) {
    return toBase;
  }
  return <UpcomingChampionship setCode={setCode} view={view} />;
}

function splitChampionshipTabs(pods: PodEventSummary[]): ChampionshipTab[] {
  const podTabs = pods.map((pod) => {
    const number = championshipPodNumber(pod.name) ?? 0;
    return { view: podView(number), label: `POD ${number}` };
  });
  return [{ view: "table", label: "GRAND FINAL" }, ...podTabs];
}

function GrandFinalPage({ event, tabs }: { event: PodEventSummary; tabs: ChampionshipTab[] }) {
  const navigate = useNavigate();
  const { data: matches } = usePodEventMatches(event.eventId);
  const { data: participants } = usePodEventParticipants(event.eventId);
  const { data: links } = useChampionshipLinks();
  const byName = useMemo(() => participantByName(participants ?? []), [participants]);
  const final = matches?.[0];
  const vodUrl = links?.find((row) => row.eventId === event.eventId)?.vodUrl;
  const openProfile = (name: string) => {
    const slug = byName.get(name)?.playerSlug;
    if (slug) {
      navigate(playerPath(slug, event.setCode));
    }
  };
  return (
    <ChampionshipShell
      setCode={event.setCode}
      label={podEventTitle(event).toUpperCase()}
      day={event.eventDate}
      media={championshipMedia(isChampionshipLive(event), vodUrl)}
      tabs={tabs}
      view="table"
      centered
    >
      <GrandFinal match={final} champion={final?.winnerName ?? null} byName={byName} onSelect={openProfile} />
    </ChampionshipShell>
  );
}

function UpcomingChampionship({ setCode, view }: { setCode: string; view: ChampionshipView }) {
  const isMobile = useIsMobile();
  const field = useChampionshipField(setCode);
  const calendarDay = useChampionshipDay(setCode);
  const day = field.eventAt ?? calendarDay;
  const identities = useMemo(
    () =>
      field.seats.map((seat) => ({
        key: seat.slug ?? seat.displayName,
        name: seat.displayName,
        avatarUrl: seat.avatarUrl,
        slug: seat.slug,
        unconfirmed: field.frozen && seat.rsvp !== "yes",
      })),
    [field.seats, field.frozen],
  );
  const { players, statsLoading } = useChampionshipPlayers(setCode, identities);

  const content =
    view === "top8" ? (
      <div
        className={
          isMobile ? "flex flex-col gap-3" : "w-full grid grid-cols-[repeat(auto-fill,minmax(420px,1fr))] gap-4"
        }
      >
        {players.map((player) => (
          <PlayerProfileCard
            key={player.key}
            player={player}
            setCode={setCode}
            loading={statsLoading || field.loading}
          />
        ))}
      </div>
    ) : (
      <QualificationList
        entrants={field.invited}
        seated={field.seats}
        frozenAt={field.frozenAt}
        setCode={setCode}
        compact={isMobile}
      />
    );

  return (
    <ChampionshipShell setCode={setCode} label={UPCOMING_LABEL} day={day} tabs={UPCOMING_TABS} view={view}>
      <div className={view === "top8" ? "w-full" : "w-full max-w-[860px] mx-auto"}>{content}</div>
    </ChampionshipShell>
  );
}

function ChampionshipShell({
  setCode,
  label,
  day,
  media = null,
  tabs,
  view,
  centered = false,
  children,
}: {
  setCode: string;
  label: string;
  day: string | null;
  media?: ChampionshipMedia | null;
  tabs: ChampionshipTab[];
  view: ChampionshipView;
  centered?: boolean;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const isMobile = useIsMobile();
  const switchView = (next: ChampionshipView) => navigate(`${championshipViewHref(setCode, next)}${location.search}`);
  const title = { setCode, label, day, media };

  if (isMobile) {
    return (
      <div className="bg-bg text-text min-h-screen flex flex-col">
        <MobilePageHeader backTo={HALL_OF_FAME_PATH} prevTo={null} nextTo={null} />
        <ChampionshipMobileTitle {...title} />
        <ChampionshipTabs tabs={tabs} view={view} onChange={switchView} className="w-full" />
        <div className="px-3 py-4">{children}</div>
      </div>
    );
  }

  return (
    <div className="bg-bg text-text h-screen flex flex-col overflow-hidden">
      <AppHeader subtitle="POD DRAFT BREAKDOWN" />
      <main className="flex-1 flex flex-col px-3 md:px-6 pb-5 min-h-0">
        <div className="h-[64px] pt-5 pb-2 grid grid-cols-[1fr_auto_1fr] items-center gap-4 shrink-0">
          <span className="flex items-center gap-4 min-w-0">
            <BackButton to={HALL_OF_FAME_PATH} label="BACK TO HALL OF FAME" inline />
            <span className="flex-1 min-w-0 flex justify-center">
              <ChampionshipTitle {...title} />
            </span>
          </span>
          <ChampionshipTabs tabs={tabs} view={view} onChange={switchView} />
          <span />
        </div>
        <div
          className={cn(
            "flex-1 min-h-0 overflow-y-auto themed-scrollbar py-4",
            centered && "flex items-center justify-center pb-[140px]",
          )}
        >
          {children}
        </div>
      </main>
    </div>
  );
}

function useChampionshipDay(setCode: string): string | null {
  const { data: calendar } = usePodCalendar();
  const entry = calendar?.find((day) =>
    day.entries.some((cell) => cell.role === "championship" && cell.glyph === setCode),
  );
  return entry?.day ?? null;
}
