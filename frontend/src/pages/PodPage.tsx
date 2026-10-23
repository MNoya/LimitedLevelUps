import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { AppHeader } from "../components/AppHeader";
import { DraftReviewMOCS, type ReviewSeatInfo } from "../components/pod/review/DraftReviewMOCS";
import { SectionLabel } from "../components/SectionLabel";
import { BackButton, MobilePageHeader, PrevNextNav } from "../components/PageNav";
import { useCloseModal } from "../lib/modal-history";
import { useIsLandscapePhone, useIsMobile } from "../lib/use-is-mobile";
import { cn } from "../lib/utils";
import { PodTable, PodTableSkeleton } from "../components/pod/PodTable";
import { PlayerSeatPanel } from "../components/pod/PlayerSeatPanel";
import type { RoundOutcome } from "../components/pod/PlayerSeatPanel";
import { MobileSeatStack, MobileSeatStackSkeleton } from "../components/pod/MobileSeatStack";
import { DeckScreenshotModal, type DeckTab } from "../components/pod/DeckScreenshotModal";
import { podDeckHref, podDraftLogHref, podPagePath, podSeatHref } from "../components/pod/podLinks";
import {
  compareStandings,
  hasStandings,
  PodStandings,
  PodStandingsSkeleton,
  StandingsBackBar,
} from "../components/pod/PodStandings";
import {
  useChampionshipEvents,
  useChampionshipLinks,
  usePodDraftArtifact,
  usePodEventBySlug,
  usePodEventMatches,
  usePodEventParticipants,
  usePodEventReplays,
  usePodEvents,
} from "../data/hooks";
import { resolveDeck } from "../data/draft-artifact";
import { usePodDecklistAccess } from "../data/podDecklistAccess";
import { useCardImageMap } from "../data/cardImages";
import { isChampionshipEvent, podDiscordName, podEventTitle, podSeatName } from "../data/utils";
import { ChampionshipBracket } from "../components/hallOfFame/ChampionshipBracket";
import { PlayerProfileCard } from "../components/hallOfFame/PlayerProfileCard";
import { useChampionship } from "../components/hallOfFame/useChampionship";
import {
  championshipMedia,
  ChampionshipMobileTitle,
  ChampionshipTabs,
  ChampionshipTitle,
  FINISHED_TABS,
  type ChampionshipTab,
} from "../components/hallOfFame/ChampionshipChrome";
import {
  championshipViewHref,
  HALL_OF_FAME_PATH,
  championshipPodNumber,
  isLiveChampionship,
  isPodView,
  podView,
  type ChampionshipView,
} from "../data/setChampionship";
import { TabButton } from "../components/TabButton";
import type {
  PodEventParticipantRow,
  PodEventSummary,
  PodSeat,
} from "../types/leaderboard";

const TABLE_MAX_WIDE = 720;
const TABLE_MAX_SHRUNK = 700;
const ANIMATION_MS = 500;
const CHROME_OFFSET = 200;
const RAIL_SLIDE_MS = 220;
const CHROME_OFFSET_LANDSCAPE = 84;
const PANEL_MIN_WIDTH = 360;
const PANEL_MIN_WIDTH_LANDSCAPE = 280;
const NAV_ROW_CLASS = "h-[64px] pt-5 pb-2 grid grid-cols-[1fr_auto_1fr] items-center gap-4 shrink-0";

function assignSeats(rows: PodEventParticipantRow[]): PodSeat[] {
  const haveRealSeats = rows.some((r) => r.seatIndex != null);
  if (haveRealSeats) {
    return rows
      .slice()
      .filter((r) => r.seatIndex != null)
      .sort((a, b) => (a.seatIndex as number) - (b.seatIndex as number))
      .map((row) => ({
        ...row,
        seatIndex: row.seatIndex as number,
        discordName: podDiscordName(row),
      }));
  }
  const ordered = rows.slice().sort(compareStandings);
  return ordered.map((row, i) => ({
    ...row,
    seatIndex: i,
    discordName: podDiscordName(row),
  }));
}

function findSeatByName(seats: PodSeat[], name: string): PodSeat | undefined {
  const lower = name.toLowerCase();
  return (
    seats.find((p) => p.discordName === name) ??
    seats.find((p) => p.displayName === name) ??
    seats.find((p) => p.discordName.toLowerCase() === lower) ??
    seats.find((p) => p.displayName.toLowerCase() === lower)
  );
}

export function PodPage({
  slugOverride,
  championshipView = "table",
  championshipTabs = FINISHED_TABS,
}: { slugOverride?: string; championshipView?: ChampionshipView; championshipTabs?: ChampionshipTab[] } = {}) {
  const params = useParams<{ slug: string }>();
  const slug = slugOverride ?? params.slug;
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const seatParam = searchParams.get("player");
  const { deckOwnerName, deckTab } = readDeckParams(searchParams, seatParam);
  const isMobile = useIsMobile();
  const isLandscapePhone = useIsLandscapePhone();
  const [highlightedSeat, setHighlightedSeat] = useState<number | null>(null);
  const [highlightedRound, setHighlightedRound] = useState<number | null>(null);
  const [highlightedOutcome, setHighlightedOutcome] = useState<RoundOutcome | null>(null);
  const [animateLayout, setAnimateLayout] = useState(false);
  const hrefWith = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) {
        next.delete(key);
      } else {
        next.set(key, value);
      }
    }
    const query = next.toString();
    return query ? `${location.pathname}?${query}` : location.pathname;
  };
  const switchView = (view: ChampionshipView) => {
    if (!event) {
      return;
    }
    setAnimateLayout(false);
    navigate(`${championshipViewHref(event.setCode, view)}${location.search}`);
  };
  const closeDeck = useCloseModal(hrefWith({ deck: null, view: null }));

  const handleRoundHover = (seat: number | null, round: number | null, outcome: RoundOutcome | null) => {
    setHighlightedSeat(seat);
    setHighlightedRound(round);
    setHighlightedOutcome(outcome);
  };

  const { data: event, isLoading: eventLoading } = usePodEventBySlug(slug);
  const eventId = event?.eventId;
  const live = isLiveChampionship(event);
  const { data: participantRows, isLoading: participantsLoading } = usePodEventParticipants(eventId, live);
  const { data: draftArtifact } = usePodDraftArtifact(eventId);
  // Warm the card-image map for the whole draft so the review's first pick paints instantly on entry.
  const warmImageItems = useMemo(
    () => (draftArtifact ? draftArtifact.cards.map((c) => ({ name: c.n, set: c.s ?? draftArtifact.set })) : []),
    [draftArtifact],
  );
  const warmedImages = useCardImageMap(warmImageItems);
  const { data: matches, isLoading: matchesLoading } = usePodEventMatches(eventId, live);
  const { data: replays, isLoading: replaysLoading } = usePodEventReplays(eventId);
  const { data: setEvents } = usePodEvents(event?.setCode);
  const decklistAccess = usePodDecklistAccess(event, participantRows);
  const isChampionship = event ? isChampionshipEvent(event.name) : false;
  const championshipPod = event ? championshipPodNumber(event.name) : null;
  const championship = useChampionship(isChampionship && event ? event : undefined, live);
  const { data: championshipEvents } = useChampionshipEvents();
  const { data: championshipLinks } = useChampionshipLinks();
  const vodUrl = championshipLinks?.find((row) => row.eventId === eventId)?.vodUrl;
  const media = isChampionship ? championshipMedia(live, vodUrl) : null;

  const seats = useMemo<PodSeat[]>(() => {
    if (!participantRows) return [];
    return assignSeats(participantRows).map((s) => ({
      ...s,
      deckColors: decklistAccess.canViewSeat(s.avatarUrl) ? s.deckColors : null,
      ...(draftArtifact ? { hasDeckList: resolveDeck(draftArtifact, s.seatIndex) !== null } : {}),
    }));
  }, [participantRows, draftArtifact, decklistAccess]);

  const participantsBySeatName = useMemo(() => {
    const m = new Map<string, PodSeat>();
    for (const s of seats) m.set(podSeatName(s), s);
    return m;
  }, [seats]);

  const standingsAvailable = hasStandings(seats);
  const selectedParticipant = useMemo(
    () => resolveSelectedSeat(seats, seatParam, isMobile && !standingsAvailable),
    [seats, seatParam, isMobile, standingsAvailable],
  );
  const selectedSeat = selectedParticipant?.seatIndex ?? null;

  const deckOwner = deckOwnerName ? findSeatByName(seats, deckOwnerName) : undefined;
  const deckTarget = deckOwner && decklistAccess.canViewSeat(deckOwner.avatarUrl) ? deckOwner : null;
  const deckTargetMainboard = useMemo(
    () => (draftArtifact && deckTarget ? resolveDeck(draftArtifact, deckTarget.seatIndex) : null),
    [draftArtifact, deckTarget],
  );
  const neighbourDeck = (direction: number): PodSeat | null => {
    if (!deckTarget) return null;
    const index = seats.findIndex((s) => s.seatIndex === deckTarget.seatIndex);
    if (index === -1) return null;
    for (let step = 1; step <= seats.length; step++) {
      const next = seats[(((index + direction * step) % seats.length) + seats.length) % seats.length];
      if (decklistAccess.canViewSeat(next.avatarUrl)) {
        return next;
      }
    }
    return null;
  };

  const siblingEvents = isChampionship
    ? championshipEvents?.filter((e) => championshipPodNumber(e.name) === null)
    : setEvents;
  const { prevEvent, nextEvent } = useMemo(() => {
    if (!siblingEvents || !event) return { prevEvent: null, nextEvent: null };
    const nowMs = Date.now();
    const started = siblingEvents.filter(
      (e) => e.championDisplayName || new Date(e.eventTime).getTime() <= nowMs,
    );
    const isCurrent = (e: PodEventSummary) =>
      isChampionship ? e.setCode === event.setCode : e.eventId === event.eventId;
    const idx = started.findIndex(isCurrent);
    if (idx < 0) return { prevEvent: null, nextEvent: null };
    return {
      prevEvent: idx > 0 ? started[idx - 1] : null,
      nextEvent: idx < started.length - 1 ? started[idx + 1] : null,
    };
  }, [siblingEvents, event, isChampionship]);
  const siblingView = isPodView(championshipView) ? "table" : championshipView;
  const showingTable = !isChampionship || championshipView === "table" || isPodView(championshipView);
  const siblingHref = (sibling: PodEventSummary | null) => {
    if (!sibling) return null;
    return isChampionship ? championshipViewHref(sibling.setCode, siblingView) : `/pods/${sibling.slug}`;
  };
  const prevTo = siblingHref(prevEvent);
  const nextTo = siblingHref(nextEvent);
  const backTo = isChampionship ? HALL_OF_FAME_PATH : "/pods";
  const backLabel = isChampionship ? "BACK TO HALL OF FAME" : "BACK TO POD DRAFTS";

  const chromeOffset = isLandscapePhone ? CHROME_OFFSET_LANDSCAPE : CHROME_OFFSET;
  const panelMinWidth = isLandscapePhone ? PANEL_MIN_WIDTH_LANDSCAPE : PANEL_MIN_WIDTH;
  const mainClass = `flex-1 flex flex-col px-3 min-h-0 ${isLandscapePhone ? "pb-2" : "md:px-6 pb-5"}`;
  const tableColumnPad = isLandscapePhone ? "py-1 pr-2" : "py-3 md:py-4 pr-5 md:pr-7";
  const contentRowPad = isLandscapePhone ? "py-1" : "py-2";
  const pageHeader = isLandscapePhone ? (
    <MobilePageHeader
      backTo={backTo}
      prevTo={prevTo}
      nextTo={nextTo}
      prevAriaLabel="Previous pod"
      nextAriaLabel="Next pod"
    />
  ) : (
    <AppHeader subtitle="POD DRAFT BREAKDOWN" />
  );

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [slug]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (deckTarget) return;
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
      const t = e.target;
      if (t instanceof HTMLElement) {
        if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable) return;
      }
      if (e.key === "ArrowLeft" && prevTo) {
        e.preventDefault();
        navigate(prevTo);
      } else if (e.key === "ArrowRight" && nextTo) {
        e.preventDefault();
        navigate(nextTo);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prevTo, nextTo, navigate, deckTarget]);

  const [lingeringParticipant, setLingeringParticipant] = useState<PodSeat | null>(selectedParticipant);
  const displayParticipant = selectedParticipant ?? lingeringParticipant;

  useEffect(() => {
    if (selectedParticipant) {
      setLingeringParticipant(selectedParticipant);
      return;
    }
    const t = setTimeout(() => setLingeringParticipant(null), ANIMATION_MS);
    return () => clearTimeout(t);
  }, [selectedParticipant]);

  useEffect(() => {
    if (!event || animateLayout) return;
    const id = window.requestAnimationFrame(() => setAnimateLayout(true));
    return () => window.cancelAnimationFrame(id);
  }, [event, animateLayout]);

  const isMock = event ? event.kind === "mock" : isMockDraftSlug(slug);
  const railOpensOnLoad = !isMock || seatParam !== null;

  if (!slugOverride && event && isChampionship) {
    const view = championshipPod === null ? "table" : podView(championshipPod);
    return <Navigate to={`${championshipViewHref(event.setCode, view)}${location.search}`} replace />;
  }

  if (eventLoading || (event && participantsLoading)) {
    if (isMobile) {
      return (
        <div className="bg-bg text-text min-h-screen flex flex-col">
          <MobilePageHeader
            backTo={backTo}
            prevTo={null}
            nextTo={null}
            prevAriaLabel="Previous pod"
            nextAriaLabel="Next pod"
          />
          {isChampionship && event ? (
            <>
              <ChampionshipMobileTitle
                setCode={event.setCode}
                label={podEventTitle(event).toUpperCase()}
                day={event.eventDate}
                media={media}
              />
              <ChampionshipTabs tabs={championshipTabs} view={championshipView} onChange={switchView} className="w-full" />
            </>
          ) : null}
          <MobileSeatStackSkeleton
            variant={seatParam || isMock ? "player" : "standings"}
            finalized={event?.isFinalized ?? true}
            teamDraft={event?.isTeamDraft ?? false}
          />
        </div>
      );
    }
    return (
      <div className="bg-bg text-text h-screen flex flex-col overflow-hidden">
        {pageHeader}
        <main className={mainClass}>
          {!isLandscapePhone && (
            <div className={NAV_ROW_CLASS}>
              <span className="flex items-center gap-4 min-w-0">
                <BackButton to={backTo} label={backLabel} inline />
                {isChampionship && event ? (
                  <span className="flex-1 min-w-0 flex justify-center">
                    <ChampionshipTitle
                      setCode={event.setCode}
                      label={podEventTitle(event).toUpperCase()}
                      day={event.eventDate}
                      media={media}
                    />
                  </span>
                ) : null}
              </span>
              {isChampionship ? <ChampionshipTabs tabs={championshipTabs} view={championshipView} onChange={switchView} /> : <span />}
            </div>
          )}
          {!showingTable ? (
            <div className="flex-1" />
          ) : railOpensOnLoad ? (
            <div className={`flex-1 flex items-stretch min-h-0 ${contentRowPad}`}>
              <div className={`flex items-center min-w-0 shrink-0 justify-end ${tableColumnPad}`} style={{ width: "55%" }}>
                <PodTableSkeleton
                  maxWidth={`min(${TABLE_MAX_SHRUNK}px, calc(100vh - ${chromeOffset}px))`}
                />
              </div>
              <div className="min-w-0 shrink-0 self-start max-h-full" style={{ width: "45%" }}>
                <PodPanelSkeleton
                  minWidth={panelMinWidth}
                  variant={seatParam ? "player" : "standings"}
                  finalized={event?.isFinalized ?? true}
                />
              </div>
            </div>
          ) : (
            <div className={`flex-1 flex items-center justify-center min-h-0 ${contentRowPad}`}>
              <PodTableSkeleton
                maxWidth={`min(${TABLE_MAX_WIDE}px, calc(100vh - ${chromeOffset}px))`}
              />
            </div>
          )}
        </main>
      </div>
    );
  }

  if (!event) {
    return (
      <div className="bg-bg text-text min-h-screen">
        <AppHeader subtitle="POD DRAFTS" />
        <main className="px-6 md:px-10 py-16 max-w-[720px]">
          <SectionLabel className="mb-3">Not found</SectionLabel>
          <h1 className="font-display text-text" style={{ fontSize: 36, letterSpacing: "0.04em" }}>
            No pod matched <span className="text-muted">"{slug}"</span>.
          </h1>
          <p className="text-muted mt-4">
            <Link to="/pods" className="text-green hover:underline">
              Back to pod drafts
            </Link>
          </p>
        </main>
      </div>
    );
  }

  const eventLabel = podEventTitle(event).toUpperCase();
  const selectSeatByName = (name: string) => {
    const seat = seats.find((entry) => entry.displayName === name);
    if (seat) {
      navigate(hrefWith({ player: podSeatName(seat) }));
    }
  };
  const openSeatInTable = (name: string) => {
    const seat = seats.find((entry) => entry.displayName === name);
    if (seat) {
      const player = new URLSearchParams({ player: podSeatName(seat) });
      navigate(`${championshipViewHref(event.setCode, "table")}?${player}`);
    }
  };
  const detailOpen = selectedParticipant !== null;
  const open = showingTable ? detailOpen || standingsAvailable : championshipView === "bracket" && detailOpen;
  const tableMaxPx = open ? TABLE_MAX_SHRUNK : TABLE_MAX_WIDE;
  const loadedMatches = matches ?? [];
  const loadedReplays = replays ?? [];
  const auxLoading = matchesLoading || replaysLoading;
  const standingsActions = {
    eventSlug: event.slug,
    hasDraftLog: !!draftArtifact,
    canViewSeat: decklistAccess.canViewSeat,
  };
  const deckHrefFor = (owner: PodSeat, tab: DeckTab) =>
    podDeckHref(location.pathname, seatParam, owner.discordName, tab);
  const replaceDeck = (href: string) => navigate(href, { replace: true, state: location.state });
  const prevDeck = neighbourDeck(-1);
  const nextDeck = neighbourDeck(1);
  const prevDeckHref = prevDeck ? deckHrefFor(prevDeck, deckTab) : undefined;
  const nextDeckHref = nextDeck ? deckHrefFor(nextDeck, deckTab) : undefined;
  const deckModal = deckTarget && (
    <DeckScreenshotModal
      participant={{
        eventId: deckTarget.eventId,
        displayName: deckTarget.discordName,
        participantDisplayName: deckTarget.displayName,
        deckColors: deckTarget.deckColors,
        deckScreenshotUrl: deckTarget.deckScreenshotUrl,
        deckScreenshotCaption: deckTarget.deckScreenshotCaption,
        mainboard: deckTargetMainboard,
        record: deckTarget.record,
      }}
      tab={deckTab}
      onTabChange={(tab) => replaceDeck(deckHrefFor(deckTarget, tab))}
      draftLogHref={draftArtifact ? podDraftLogHref(event.slug, deckTarget) : null}
      cardImages={warmedImages}
      onClose={closeDeck}
      onPrev={prevDeckHref ? () => replaceDeck(prevDeckHref) : undefined}
      onNext={nextDeckHref ? () => replaceDeck(nextDeckHref) : undefined}
      prevHref={prevDeckHref}
      nextHref={nextDeckHref}
    />
  );

  if (isMobile) {
    return (
      <div className="bg-bg text-text min-h-screen flex flex-col">
        <MobilePageHeader
          backTo={backTo}
          prevTo={prevTo}
          nextTo={nextTo}
          prevAriaLabel="Previous pod"
          nextAriaLabel="Next pod"
        />
        {isChampionship ? (
          <>
            <ChampionshipMobileTitle setCode={event.setCode} label={eventLabel} day={event.eventDate} media={media} />
            <ChampionshipTabs tabs={championshipTabs} view={championshipView} onChange={switchView} className="w-full" />
          </>
        ) : null}
        {isChampionship && championshipView === "bracket" ? (
          <div className="px-3 py-4">
            <ChampionshipBracket
              bracket={championship.bracket}
              champion={championship.champion}
              byName={championship.byName}
              showDecks={decklistAccess.canViewAll}
              onSelect={(name) => openSeatInTable(name)}
            />
          </div>
        ) : isChampionship && championshipView === "top8" ? (
          <div className="px-3 py-4 flex flex-col gap-3">
            {championship.players.map((player) => (
              <PlayerProfileCard
                key={player.key}
                player={player}
                setCode={event.setCode}
                loading={championship.statsLoading}
              />
            ))}
          </div>
        ) : (
          <MobileSeatStack
            participants={seats}
            participantsBySeatName={participantsBySeatName}
            matches={loadedMatches}
            replays={loadedReplays}
            selectedSeat={selectedSeat}
            canViewSeat={decklistAccess.canViewSeat}
            podFinalized={event.isFinalized}
            eventLabel={eventLabel}
            setCode={event.setCode}
            eventSlug={event.slug}
            hasDraftLog={!!draftArtifact}
            formatLabel={event.formatLabel}
            isMock={isMock}
            standingsAvailable={standingsAvailable}
            teamDraft={event.isTeamDraft ?? false}
            standingsActions={standingsActions}
          />
        )}
        {deckModal}
      </div>
    );
  }

  return (
    <div className="bg-bg text-text h-screen flex flex-col overflow-hidden">
      {pageHeader}

      <main className={mainClass}>
        {!isLandscapePhone && (
          <div className={NAV_ROW_CLASS}>
            <span className="flex items-center gap-4 min-w-0">
              <BackButton to={backTo} label={backLabel} inline />
              {isChampionship ? (
                <span className="flex-1 min-w-0 flex justify-center">
                  <ChampionshipTitle setCode={event.setCode} label={eventLabel} day={event.eventDate} media={media} />
                </span>
              ) : null}
            </span>
            {isChampionship ? <ChampionshipTabs tabs={championshipTabs} view={championshipView} onChange={switchView} /> : <span />}
            <span className="justify-self-end">
              <PrevNextNav
                prevTo={prevTo}
                nextTo={nextTo}
                prevAriaLabel="Previous pod"
                nextAriaLabel="Next pod"
              />
            </span>
          </div>
        )}

        <div className={`flex-1 flex items-stretch min-h-0 ${contentRowPad}`}>
          <div
            className={`flex items-center min-w-0 shrink-0 ${tableColumnPad} ${open ? "justify-end" : "justify-center"}`}
            style={{
              width: open ? "55%" : "100%",
              transition: animateLayout ? `width ${ANIMATION_MS}ms ease-out` : "none",
            }}
          >
            {isChampionship && championshipView === "bracket" ? (
              <div className="w-full self-stretch flex flex-col items-center">
                <span className="flex-[1_1_0px]" />
                <ChampionshipBracket
                  bracket={championship.bracket}
                  champion={championship.champion}
                  byName={championship.byName}
                  showDecks={decklistAccess.canViewAll && !open}
                  large={!open}
                  selected={selectedParticipant?.displayName ?? null}
                  onSelect={selectSeatByName}
                />
                <span className="flex-[1_1_140px]" />
              </div>
            ) : isChampionship && championshipView === "top8" ? (
              <div className="w-full grid grid-cols-[repeat(auto-fill,minmax(420px,1fr))] gap-4 self-start">
                {championship.players.map((player) => (
                  <PlayerProfileCard
                    key={player.key}
                    player={player}
                    setCode={event.setCode}
                    loading={championship.statsLoading}
                  />
                ))}
              </div>
            ) : (
              <PodTable
                participants={seats}
                selectedSeat={selectedSeat}
                highlightedSeat={highlightedSeat}
                highlightedRound={highlightedRound}
                highlightedOutcome={highlightedOutcome}
                canViewDeck={decklistAccess.canViewSeat}
                eventLabel={eventLabel}
                teamDraft={event.isTeamDraft ?? false}
                eventSlug={event.slug}
                hasDraftLog={!!draftArtifact}
                setCode={event.setCode}
                formatLabel={event.formatLabel}
                date={event.eventDate}
                maxWidth={`min(${tableMaxPx}px, calc(100vh - ${chromeOffset}px))`}
              />
            )}
          </div>
          <div
            className="min-w-0 shrink-0 self-start max-h-full flex flex-col min-h-0"
            style={{
              width: open ? "45%" : "0%",
              opacity: open ? 1 : 0,
              transition: animateLayout
                ? `width ${ANIMATION_MS}ms ease-out, opacity ${ANIMATION_MS - 80}ms ease-out`
                : "none",
            }}
          >
            <div className="pod-panel-shell bg-surface border border-border flex flex-col min-h-0 flex-1 overflow-hidden">
              <div className="relative flex flex-col min-h-0 flex-1" style={{ minWidth: panelMinWidth }}>
                {standingsAvailable && (
                  <RailLayer shown={!detailOpen} hiddenShift="-translate-x-4" className="overflow-y-auto themed-scrollbar">
                    <PodStandings
                      seats={seats}
                      teamDraft={event.isTeamDraft ?? false}
                      finalized={event.isFinalized}
                      selectedSeat={selectedSeat}
                      onHover={(seat) => handleRoundHover(seat, null, null)}
                      actions={standingsActions}
                      highlightChampion={isChampionship && championshipPod === null}
                    />
                  </RailLayer>
                )}
                <RailLayer shown={detailOpen || !standingsAvailable} hiddenShift="translate-x-6">
                  {standingsAvailable && (
                    <StandingsBackBar
                      to={hrefWith({ player: null })}
                      label={championshipView === "bracket" ? "BACK TO BRACKET" : "BACK TO STANDINGS"}
                    />
                  )}
                  {displayParticipant && (
                    <PlayerSeatPanel
                      key={displayParticipant.displayName}
                      participant={displayParticipant}
                      participantsBySeatName={participantsBySeatName}
                      matches={loadedMatches}
                      replays={loadedReplays}
                      setCode={event.setCode}
                      eventSlug={event.slug}
                      hasDraftLog={!!draftArtifact}
                      canViewSeat={decklistAccess.canViewSeat}
                      podFinalized={event.isFinalized}
                      onRoundHover={handleRoundHover}
                      isMock={isMock}
                    />
                  )}
                  {displayParticipant && auxLoading && (
                    <div className="px-5 py-2 text-muted text-[12px] font-body">
                      Loading matches & replays…
                    </div>
                  )}
                </RailLayer>
              </div>
            </div>
          </div>
        </div>
      </main>
      {deckModal}
    </div>
  );
}

const readDeckParams =(params: URLSearchParams, seatParam: string | null) => {
  const deck = params.get("deck");
  const poolView = params.get("view") === "pool";
  const legacyTab = deck === "screenshot" || deck === "decklist";
  const deckTab: DeckTab = poolView || deck === "decklist" ? "decklist" : "screenshot";
  return { deckOwnerName: legacyTab ? seatParam : deck, deckTab };
};

const isMockDraftSlug = (slug: string | undefined) => slug?.includes("-mock-draft-") ?? false;

const resolveSelectedSeat = (seats: PodSeat[], seatName: string | null, alwaysSelect: boolean) => {
  const named = seatName ? findSeatByName(seats, seatName) : undefined;
  if (named) {
    return named;
  }
  if (!alwaysSelect) {
    return null;
  }
  return seats.find((p) => p.placement === 1) ?? seats[0] ?? null;
};

export function PodDraftLogRoute() {
  const { slug, who, pack, pick } = useParams<{ slug: string; who?: string; pack?: string; pick?: string }>();
  const { data: event, isLoading: eventLoading } = usePodEventBySlug(slug);
  const eventId = event?.eventId;
  const { data: participantRows, isLoading: participantsLoading } = usePodEventParticipants(eventId);
  const { data: artifact, isLoading: artifactLoading } = usePodDraftArtifact(eventId);
  const decklistAccess = usePodDecklistAccess(event, participantRows);

  const seats = useMemo(
    () => (participantRows ? assignSeats(participantRows) : []),
    [participantRows],
  );

  if (eventLoading || (event && (participantsLoading || artifactLoading))) {
    return <div className="fixed inset-0 z-50 bg-bg" />;
  }
  if (!event || !artifact) {
    return <Navigate to={`/pods/${slug ?? ""}`} replace />;
  }

  if (!who) {
    return <Navigate to={`/pods/${slug}`} replace />;
  }

  const resolved = resolveLogSeat(seats, who);
  const seatIndex = resolved != null && resolved < artifact.seats.length ? resolved : 0;
  const seatInfo: ReviewSeatInfo[] = seats.map((s) => ({
    seatIndex: s.seatIndex,
    playerSlug: s.playerSlug,
    displayName: s.discordName,
    participantDisplayName: s.displayName,
    avatarUrl: s.avatarUrl,
    deckColors: s.deckColors,
    deckScreenshotUrl: s.deckScreenshotUrl,
    deckScreenshotCaption: s.deckScreenshotCaption,
    record: s.record,
  }));

  const current = resolved != null ? seats.find((s) => s.seatIndex === resolved) : null;
  const backHref = podSeatHref(podPagePath(event.slug), current?.discordName ?? null);

  // While the pod is closed a player gets their own draft in scroll-only mode; only organizers and
  // finished pods open the whole-table review.
  const soloOwnSeat = !decklistAccess.canViewAll;
  if (soloOwnSeat && !(current && decklistAccess.canViewSeat(current.avatarUrl))) {
    return <Navigate to={`/pods/${slug}`} replace />;
  }

  return (
    <DraftReviewMOCS
      artifact={artifact}
      meta={{ setCode: event.setCode, name: event.name }}
      seat={seatIndex}
      pack={pack ? Number(pack) - 1 : 0}
      pick={pick ? Number(pick) - 1 : 0}
      backHref={backHref}
      eventSlug={event.slug}
      eventId={event.eventId}
      seatInfo={seatInfo}
      soloSeat={soloOwnSeat ? seatIndex : undefined}
    />
  );
}

function resolveLogSeat(seats: PodSeat[], who: string): number | null {
  const bySlug = seats.find((s) => s.playerSlug === who);
  if (bySlug) {
    return bySlug.seatIndex;
  }
  const n = Number(who);
  if (Number.isInteger(n) && seats.some((s) => s.seatIndex === n)) {
    return n;
  }
  return null;
}

function RailLayer({
  shown,
  hiddenShift,
  className,
  children,
}: {
  shown: boolean;
  hiddenShift: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      aria-hidden={!shown}
      className={cn(
        "flex flex-col ease-out motion-reduce:transition-none transition-[transform,opacity]",
        shown
          ? "relative flex-1 min-h-0 translate-x-0 opacity-100"
          : `absolute inset-0 ${hiddenShift} opacity-0 pointer-events-none`,
        className,
      )}
      style={{ transitionDuration: `${RAIL_SLIDE_MS}ms` }}
    >
      {children}
    </div>
  );
}

function PodPanelSkeleton({
  minWidth = PANEL_MIN_WIDTH,
  variant = "player",
  finalized = true,
}: {
  minWidth?: number;
  variant?: "player" | "standings";
  finalized?: boolean;
}) {
  if (variant === "standings") {
    return (
      <div className="pod-panel-shell bg-surface border border-border max-h-full overflow-hidden">
        <div style={{ minWidth }}>
          <PodStandingsSkeleton finalized={finalized} />
        </div>
      </div>
    );
  }
  return (
    <div className="pod-panel-shell bg-surface border border-border max-h-full overflow-hidden">
      <div style={{ minWidth }}>
        <div className="flex items-center gap-4 px-4 md:px-5 xl:px-8 py-5 border-b border-border">
          <div className="w-[54px] h-[54px] bg-surface2 animate-pulse shrink-0" />
          <div className="min-w-0 flex-1 flex flex-col gap-2">
            <div className="h-7 w-2/3 bg-surface2 animate-pulse" />
            <div className="h-4 w-1/3 bg-surface2 animate-pulse" />
          </div>
          <div className="flex flex-col gap-2 shrink-0">
            <div className="h-[44px] w-[200px] bg-surface2 animate-pulse" />
            <div className="h-[44px] w-[200px] bg-surface2 animate-pulse" />
          </div>
        </div>
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="border-b border-border last:border-b-0 px-4 md:px-5 xl:px-8 py-3 flex items-center gap-3">
            <div className="h-[52px] w-[72px] bg-surface2 animate-pulse" />
            <div className="h-5 w-8 bg-surface2 animate-pulse" />
            <div className="h-5 flex-1 bg-surface2 animate-pulse" />
            <div className="h-[34px] w-[120px] bg-surface2 animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}

