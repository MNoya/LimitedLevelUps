import { useMemo, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
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
import { DeckScreenshotModal } from "../components/pod/DeckScreenshotModal";
import { PodPagePathProvider } from "../components/pod/podLinks";
import { QualificationList } from "../components/hallOfFame/QualificationList";
import { useChampionshipEvent, useChampionshipPlayers } from "../components/hallOfFame/useChampionship";
import { useChampionshipField } from "../components/hallOfFame/useChampionshipField";
import { useChampionshipLinks, usePodCalendar, usePodEventMatches, usePodEventParticipants } from "../data/hooks";
import { OPENED_IN_APP, useCloseModal } from "../lib/modal-history";
import { useIsMobile } from "../lib/use-is-mobile";
import { cn } from "../lib/utils";
import { podEventTitle } from "../data/utils";
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
      return <GrandFinalPage event={event} pods={pods} tabs={tabs} />;
    }
    const pod = pods.find((entry) => podView(championshipPodNumber(entry.name) ?? 0) === view);
    return pod ? <HostedPodPage slug={pod.slug} view={view} tabs={tabs} /> : toBase;
  }
  if (event && started) {
    return isPodView(view) ? toBase : <HostedPodPage slug={event.slug} view={view} />;
  }
  if (isLoading) {
    return null;
  }
  if (view === "bracket" || isPodView(view)) {
    return toBase;
  }
  return <UpcomingChampionship setCode={setCode} view={view} />;
}

function HostedPodPage({ slug, view, tabs }: { slug: string; view: ChampionshipView; tabs?: ChampionshipTab[] }) {
  const location = useLocation();
  const hosted = useMemo(() => ({ slug, path: location.pathname }), [slug, location.pathname]);
  return (
    <PodPagePathProvider value={hosted}>
      <PodPage slugOverride={slug} championshipView={view} championshipTabs={tabs} />
    </PodPagePathProvider>
  );
}

function splitChampionshipTabs(pods: PodEventSummary[]): ChampionshipTab[] {
  const podTabs = pods.map((pod) => {
    const number = championshipPodNumber(pod.name) ?? 0;
    return { view: podView(number), label: `POD ${number}` };
  });
  return [{ view: "table", label: "GRAND FINAL" }, ...podTabs];
}

function GrandFinalPage({
  event,
  pods,
  tabs,
}: {
  event: PodEventSummary;
  pods: PodEventSummary[];
  tabs: ChampionshipTab[];
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { data: matches } = usePodEventMatches(event.eventId);
  const { data: participants } = usePodEventParticipants(event.eventId);
  const { data: links } = useChampionshipLinks();
  const byName = useMemo(() => participantByName(participants ?? []), [participants]);
  const final = matches?.[0];
  const vodUrl = links?.find((row) => row.eventId === event.eventId)?.vodUrl;
  const finalists = final ? [final.playerAName, final.playerBName] : [];
  const deckOwner = searchParams.get("deck");
  const deckParticipant = deckOwner ? byName.get(deckOwner) : undefined;
  const deckHref = (name: string) => `${location.pathname}?${new URLSearchParams({ deck: name })}`;
  const closeDeck = useCloseModal(location.pathname);
  const openDeck = (name: string) => navigate(deckHref(name), { state: OPENED_IN_APP });
  const switchDeck = (name: string) => navigate(deckHref(name), { replace: true, state: location.state });
  const otherFinalist = finalists.find((name) => name !== deckOwner);
  const podTabFor = (name: string) => {
    const pod = pods.find((entry) => entry.championDisplayName === name);
    if (!pod) {
      return undefined;
    }
    const view = podView(championshipPodNumber(pod.name) ?? 0);
    return `${championshipViewHref(event.setCode, view)}?${new URLSearchParams({ player: name })}`;
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
      <GrandFinal match={final} champion={final?.winnerName ?? null} byName={byName} onSelect={openDeck} />
      {deckOwner && deckParticipant ? (
        <DeckScreenshotModal
          participant={{
            eventId: event.eventId,
            displayName: deckOwner,
            participantDisplayName: deckParticipant.displayName,
            deckColors: deckParticipant.deckColors,
            deckScreenshotUrl: deckParticipant.deckScreenshotUrl,
            deckScreenshotCaption: deckParticipant.deckScreenshotCaption,
            record: deckParticipant.record,
          }}
          breakdownHref={podTabFor(deckOwner)}
          hideDraftLog
          onClose={closeDeck}
          onPrev={otherFinalist ? () => switchDeck(otherFinalist) : undefined}
          onNext={otherFinalist ? () => switchDeck(otherFinalist) : undefined}
          prevHref={otherFinalist ? deckHref(otherFinalist) : undefined}
          nextHref={otherFinalist ? deckHref(otherFinalist) : undefined}
        />
      ) : null}
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
