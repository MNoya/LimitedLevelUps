import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { useNow } from "../../lib/countdown";
import { Check, Eye, EyeOff, Lock, Plus, Repeat } from "lucide-react";
import { Tooltip } from "../Tooltip";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { usePersistentBool } from "../../lib/use-persistent-bool";
import { DiscordIcon } from "../BrandIcons";
import { ChevronDown } from "../Icons";
import { SectionLabel } from "../SectionLabel";
import { cn } from "../../lib/utils";
import { useIsMobile } from "../../lib/use-is-mobile";
import {
  CountryFlag,
  PlayerPortrait,
  QUALIFICATION_ORDER,
  QualificationChips,
  SLOTS,
  SearchBox,
  fullName,
  playerSlug,
  cardName,
  FitText,
  PicksCountdown,
  PicksLockDate,
  qualificationLabel,
  qualificationOf,
  shortLastName,
  slotFor,
  useFieldFilters,
  useLineupPicker,
  type FieldPlayer,
  type Lineup,
  type Qualification,
  type Slot,
  type SlotKey,
} from "./fantasyField";
import { PickButton, PlayerProfile, PlayerProfileSheet } from "./PlayerProfilePanel";
import {
  EventCrest,
  EventSwitcher,
  EventTitle,
  ProfileHint,
  FieldTile,
  HoverCard,
  useHoverTarget,
  useLongPress,
} from "./FantasyParts";
import { TabLink } from "../TabButton";
import { useAuth } from "../../auth/useAuth";
import { LeaderboardSkeleton, MembersLeaderboard } from "./MembersLeaderboard";
import { ReplayStandings, StandingsSkeleton } from "./ReplayStandings";
import { replayProfileEvent, standingsAfter, standingsRound } from "./fantasyReplay";
import { usePersistedLineup } from "./usePersistedLineup";
import {
  FantasyEventContext,
  fantasyEventByCode,
  fantasyEventPath,
  useFantasyEvent,
  type FantasyEventHeader,
} from "./fantasyEvents";
import { Top8Bracket, Top8BracketList } from "./Top8Bracket";
import { eventContext, membersFromRows, standings, type Member, type StandingsDay } from "./fantasyMembers";
import { type BracketPicks } from "./fantasyTop8";
import { dayOneRecord, isOut, playerPoints, recordThrough, type EventPhase } from "./fantasyScoring";
import { LiveEventContext, buildLiveEvent, liveBracketResults, useLiveEvent, type LiveEvent } from "./fantasyLive";
import { usePersistedBracket } from "./usePersistedBracket";
import { useFantasyEventState, useFantasyField, useFantasyMembers, useFantasyResults } from "../../data/hooks";
import type { FantasyBracketPickRow, FantasyLineupRow, FantasyMemberRow } from "../../types/fantasy";


type Picker = ReturnType<typeof useLineupPicker>;
type Filters = ReturnType<typeof useFieldFilters>;

type SheetView = "field" | "standings" | "top8" | "leaderboard";

export function TeamSheet({ loginCta, onSignIn }: { loginCta: ReactNode; onSignIn: () => void }) {
  const header = useFantasyEvent();
  const entry = fantasyEventByCode(header.code);
  const [spoilerFree, setSpoilerFree] = usePersistentBool("fantasySpoilerFree", true);
  const now = useNow(15_000);
  const { data: state } = useFantasyEventState(header.code);
  const { data: field } = useFantasyField(header.code);
  const { data: results } = useFantasyResults(header.code, state?.completedThroughRound);
  const locked = state ? now >= new Date(state.picksLockAt).getTime() : false;
  const bracketLocked = state ? now >= new Date(state.bracketLockAt).getTime() : false;
  const membersVersion = state && locked ? `${state.completedThroughRound}:${bracketLocked}` : undefined;
  const { data: members } = useFantasyMembers(header.code, membersVersion);
  const throughRound = state ? (spoilerFree ? state.revealedThroughRound : state.completedThroughRound) : 0;
  const minute = Math.floor(now / 60_000);
  const liveEvent = useMemo(
    () => {
      if (!entry || !state || !field) {
        return null;
      }
      return buildLiveEvent(entry, state, field, results ?? [], throughRound, new Date(now));
    },
    [entry, state, field, results, throughRound, minute],
  );
  const liveHeader = useMemo(
    () =>
      state
        ? {
            ...header,
            picksLockAt: new Date(state.picksLockAt),
            bracketLockAt: new Date(state.bracketLockAt),
          }
        : header,
    [header, state],
  );
  if (!liveEvent) {
    return <main className="flex-1" />;
  }
  return (
    <FantasyEventContext.Provider value={liveHeader}>
      <LiveEventContext.Provider value={liveEvent}>
        <TeamSheetView
          loginCta={loginCta}
          onSignIn={onSignIn}
          liveEvent={liveEvent}
          members={members}
          spoilerFree={spoilerFree}
          onToggleSpoilerFree={() => setSpoilerFree((value) => !value)}
        />
      </LiveEventContext.Provider>
    </FantasyEventContext.Provider>
  );
}

function TeamSheetView({
  loginCta,
  onSignIn,
  liveEvent,
  members,
  spoilerFree,
  onToggleSpoilerFree,
}: {
  loginCta: ReactNode;
  onSignIn: () => void;
  liveEvent: LiveEvent;
  members: { members: FantasyMemberRow[]; lineups: FantasyLineupRow[]; brackets: FantasyBracketPickRow[] } | undefined;
  spoilerFree: boolean;
  onToggleSpoilerFree: () => void;
}) {
  const fantasyEvent = useFantasyEvent();
  const { cardAreaRef, cardWidth, cardAreaMinHeight } = useFittedCardWidth();
  const picker = useLineupPicker();
  const now = useNow(15_000);
  const picksOpen = now < fantasyEvent.picksLockAt.getTime();
  const phase = liveEvent.phase;
  const roundsPlayed = liveEvent.roundsPlayed;
  const live = phase !== "picking";
  const replacing = phase === "cut" && liveEvent.replacementsOpen;
  const dayOneLineup = usePersistedLineup(picker, liveEvent, !loginCta, (!live && picksOpen) || replacing);
  const filters = useFieldFilters(liveEvent.players);
  const isMobile = useIsMobile(1024);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const sheetSlug = searchParams.get("player");
  const sheetPlayer = sheetSlug ? (liveEvent.bySlug.get(sheetSlug) ?? null) : null;
  const { hoverTarget, onHover: handleHover, onLeave: handleLeave } = useHoverTarget(isMobile);
  const activeSlot = picker.activeSlot ? slotFor(picker.activeSlot) : null;
  const { view: viewSlug } = useParams();
  const defaultView = defaultViewFor(phase);
  const view = sheetViewFromSlug(viewSlug) ?? defaultView;
  const viewPath = (option: SheetView) => {
    const basePath = fantasyEventPath(liveEvent.event);
    return option === defaultView ? basePath : `${basePath}/${SHEET_VIEW_SLUG[option]}`;
  };
  const seeded = liveEvent.seeded;
  const results = liveBracketResults(liveEvent);
  const topEightOpen = phase === "top8" || phase === "final";
  const bracketOpen = liveEvent.bracketWindowOpen && now < fantasyEvent.bracketLockAt.getTime() && !results;
  const [bracketPicks, setBracketPicks] = usePersistedBracket(liveEvent, !loginCta, bracketOpen);

  const replacingSlot = picker.activeSlot && picker.lineup[picker.activeSlot] ? picker.activeSlot : null;

  useEffect(() => {
    if (!replacingSlot) {
      return;
    }
    const cancelOnOutsidePress = (event: PointerEvent) => {
      const target = event.target as Element | null;
      if (!target?.closest("[data-fantasy-pick-target]")) {
        picker.setActiveSlot(null);
      }
    };
    document.addEventListener("pointerdown", cancelOnOutsidePress);
    return () => document.removeEventListener("pointerdown", cancelOnOutsidePress);
  }, [replacingSlot]);

  const slotIsReplaceable = (key: SlotKey) => {
    const player = picker.lineup[key];
    const original = dayOneLineup?.[key];
    return replacing && Boolean(player && original && isOut(liveEvent, original));
  };

  const allMembers = useMemo(
    () => (members ? membersFromRows(liveEvent, members.members, members.lineups, members.brackets) : []),
    [liveEvent, members],
  );
  const savedSelf = allMembers.find((member) => member.isSelf);
  const selfMember: Member | null =
    savedSelf && dayOneLineup
      ? { ...savedSelf, dayOneLineup, lineup: picker.lineup, bracket: bracketPicks }
      : null;
  const others = allMembers.filter((member) => !member.isSelf);
  const memberRows = live ? standings(selfMember ? [selfMember, ...others] : others, eventContext(liveEvent)) : [];
  const memberCount = allMembers.length;
  const selfRow = memberRows.find((row) => row.member.isSelf);
  const standingsDays: StandingsDay[] = topEightOpen ? ["overall", "day1", "day2", "top8"] : ["overall", "day1", "day2"];

  const cardPoints = (key: SlotKey) => (live ? selfRow?.slots.find((slot) => slot.slot === key)?.total : undefined);

  const replacedPick = (key: SlotKey) => {
    const original = dayOneLineup?.[key];
    const current = picker.lineup[key];
    if (!original || !current || fullName(original) === fullName(current)) {
      return undefined;
    }
    return original;
  };

  const replacedPickPoints = (key: SlotKey) => {
    const replaced = replacedPick(key);
    return replaced ? playerPoints(liveEvent, replaced, key, 1, liveEvent.cutRound) : undefined;
  };

  const replacedSlotByName = new Map<string, SlotKey>();
  for (const slot of SLOTS) {
    const replaced = replacedPick(slot.key);
    if (replaced) {
      replacedSlotByName.set(fullName(replaced), slot.key);
    }
  }

  const cardOut = (key: SlotKey) => {
    const player = picker.lineup[key];
    return live && Boolean(player && isOut(liveEvent, player));
  };

  const selectCard = (key: SlotKey) => {
    if (!live && picksOpen) {
      picker.setActiveSlot(key);
      return;
    }
    if (live && slotIsReplaceable(key)) {
      picker.setActiveSlot(picker.activeSlot === key ? null : key);
      return;
    }
    const player = picker.lineup[key];
    if (player) {
      openProfile(player);
    }
  };

  const score = selfRow?.total ?? 0;
  const liveStatus = (short: boolean) =>
    live ? (
      <LiveStatus
        phase={phase}
        roundsPlayed={roundsPlayed}
        score={score}
        rank={selfRow?.rank ?? null}
        memberCount={memberCount}
        short={short}
        spoilerControl={<SpoilerEye on={spoilerFree} onToggle={onToggleSpoilerFree} />}
      />
    ) : null;


  const isPicked = (player: FieldPlayer) => picker.pickedSlotByName.has(fullName(player));

  const handleTileClick = (player: FieldPlayer) => {
    handleLeave();
    if (!live && picksOpen) {
      picker.toggle(player);
      return;
    }
    const targetSlot = live ? replacementTargetSlot() : null;
    if (targetSlot && !isPicked(player) && !isOut(liveEvent, player)) {
      picker.assign(player, targetSlot);
      return;
    }
    openProfile(player);
  };

  const replacementTargetSlot = () => {
    if (picker.activeSlot && slotIsReplaceable(picker.activeSlot)) {
      return picker.activeSlot;
    }
    for (const slot of SLOTS) {
      if (slotIsReplaceable(slot.key) && cardOut(slot.key)) {
        return slot.key;
      }
    }
    return null;
  };

  const clickPicks = (!live && picksOpen) || (live && replacementTargetSlot() !== null);

  const profileSearch = (player: FieldPlayer) => {
    const params = new URLSearchParams(searchParams);
    params.set("player", playerSlug(player));
    return `?${params.toString()}`;
  };

  const openProfile = (player: FieldPlayer) => {
    handleLeave();
    navigate(profileSearch(player), { state: { fromField: true } });
  };

  const standingsSource = liveEvent;
  const sheetOrder = useMemo(() => {
    if (view === "standings" && live) {
      const round = standingsRound(standingsSource, searchParams.get("round"));
      return standingsAfter(standingsSource, round).map((row) => row.player);
    }
    if (view === "top8" && topEightOpen) {
      return seeded;
    }
    return fieldGroups(filters.players).flatMap((group) => group.players);
  }, [view, live, topEightOpen, standingsSource, searchParams, seeded, filters.players]);
  const sheetName = sheetPlayer ? fullName(sheetPlayer) : null;
  const sheetIndex = sheetOrder.findIndex((player) => fullName(player) === sheetName);
  const neighborSearch = (offset: number) => {
    const neighbor = sheetIndex >= 0 ? sheetOrder[sheetIndex + offset] : undefined;
    return neighbor ? profileSearch(neighbor) : undefined;
  };

  const profileEventFor = (player: FieldPlayer) =>
    roundsPlayed > 0 ? replayProfileEvent(liveEvent, player, (opponent) => profileSearch(opponent)) : undefined;

  const closeProfile = () => {
    if ((location.state as { fromField?: boolean } | null)?.fromField) {
      navigate(-1);
      return;
    }
    const params = new URLSearchParams(searchParams);
    params.delete("player");
    navigate({ search: params.toString() }, { replace: true });
  };

  const profileSheet = sheetPlayer ? (
    <PlayerProfileSheet
      player={sheetPlayer}
      event={profileEventFor(sheetPlayer)}
      footer={
        live ? null : (
          <PickButton
            activeSlot={activeSlot}
            inLineup={isPicked(sheetPlayer)}
            onToggle={() => {
              picker.toggle(sheetPlayer);
              closeProfile();
            }}
          />
        )
      }
      prevHref={neighborSearch(-1)}
      nextHref={neighborSearch(1)}
      onClose={closeProfile}
    />
  ) : null;

  const field = (
    <FieldGroups
      picker={picker}
      filters={filters}
      compact={isMobile}
      replacedSlotByName={replacedSlotByName}
      onTileClick={handleTileClick}
      onTileLongPress={openProfile}
      onTileHover={handleHover}
      onTileLeave={handleLeave}
    />
  );

  const leaderboard = (
    <MembersLeaderboard
      rows={memberRows}
      days={standingsDays}
      results={results}
      seeded={seeded}
      compact={isMobile}
      onInspect={openProfile}
      onHover={handleHover}
      onLeave={handleLeave}
    />
  );
  const bracketProps = {
    seeded,
    picks: bracketPicks,
    results,
    onChange: bracketOpen ? setBracketPicks : undefined,
    onInspect: openProfile,
    onHover: handleHover,
    onLeave: handleLeave,
  };
  const bracket = isMobile ? <Top8BracketList {...bracketProps} /> : <Top8Bracket {...bracketProps} />;
  const standingsView = live ? (
    <ReplayStandings
      source={standingsSource}
      compact={isMobile}
      onOpen={openProfile}
      onHover={handleHover}
      onLeave={handleLeave}
    />
  ) : (
    <ViewPlaceholder
      backdrop={<StandingsSkeleton compact={isMobile} rows={16} />}
      title="Standings appear after Round 1"
      detail="Follow every player's rank and record round by round"
      at={<PicksLockDate size={14} prefix="Round 1 starts" at={fantasyEvent.picksLockAt} />}
    />
  );
  const bracketView = topEightOpen ? (
    bracket
  ) : (
    <ViewPlaceholder
      backdrop={isMobile ? <Top8BracketList seeded={[]} results={null} /> : <Top8Bracket seeded={[]} results={null} />}
      title="Top 8 Bracket opens after the last Swiss round"
      detail="Pick who wins each Top 8 match to add points to your total"
    />
  );
  const leaderboardView = live ? (
    leaderboard
  ) : (
    <ViewPlaceholder
      backdrop={<LeaderboardSkeleton compact={isMobile} rows={14} />}
      title="Leaderboard starts after Round 1"
      detail="Follow every member's team and points round by round"
      at={<PicksLockDate size={14} prefix="Round 1 starts" at={fantasyEvent.picksLockAt} />}
    />
  );
  const viewTabs = (
    <div className="flex border-b border-border">
      {SHEET_VIEWS.map((option) => (
        <TabLink key={option} active={view === option} to={viewPath(option)}>
          {VIEW_LABEL[option]}
        </TabLink>
      ))}
    </div>
  );
  const showField = view === "field";
  const viewBody = { field, standings: standingsView, top8: bracketView, leaderboard: leaderboardView }[view];

  if (isMobile) {
    return (
      <main className="flex-1 pb-[190px]">
        <MobileHeader status={liveStatus(true)} />
        <div className="sticky top-0 z-10 bg-bg/95 backdrop-blur border-b border-border">
          {viewTabs}
          {showField ? (
            <div className="px-3 py-2.5 flex flex-col gap-2">
              <SearchBox value={filters.search} onChange={filters.setSearch} className="w-full" />
              <div className="-mx-3 px-3 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
                <div className="w-max">
                  <QualificationChips
                    active={filters.qualification}
                    onChange={filters.setQualification}
                    players={liveEvent.players}
                  />
                </div>
              </div>
            </div>
          ) : null}
        </div>
        <div className="px-3 pt-3">{viewBody}</div>
        <MobileTray
          picker={picker}
          cta={live ? null : loginCta}
          showSaved={!live}
          onOpenProfile={openProfile}
          onSelect={selectCard}
          cardPoints={cardPoints}
          cardOut={cardOut}
        />
        {profileSheet}
      </main>
    );
  }

  return (
    <main className="flex-1 min-h-0 grid grid-cols-[510px_1fr] overflow-hidden">
      <section className="themed-scrollbar h-full border-r border-border bg-surface px-6 py-6 flex flex-col min-h-0 overflow-y-auto">
        <div className="flex justify-center">
          <EventTitle
            event={fantasyEvent}
            switcher={<EventSwitcher activeCode={fantasyEvent.code} />}
            crest={eventCrest(fantasyEvent, 56)}
            crestRaised
            labelSize={13}
            glyphSize={36}
            titleSize={42}
            citySize={18}
          />
        </div>
        {live ? (
          <div className="mt-3 flex flex-col items-center gap-3">{liveStatus(false)}</div>
        ) : (
          <div className="mt-3 flex flex-col items-center gap-0.5">
            <PicksPremise compact={false} />
            <PicksCountdown size={13} />
            <PicksLockDate size={13} prefix="Round 1 starts" at={fantasyEvent.picksLockAt} />
          </div>
        )}

            <div
              ref={cardAreaRef}
              className="flex-1 flex flex-col items-center justify-center gap-5 py-3"
              style={{ minHeight: cardAreaMinHeight }}
            >
              {phase === "cut" ? <CutNote /> : null}
              <div className="grid grid-cols-2 gap-x-5 gap-y-4">
                {SLOTS.map((slot) => {
                  const player = picker.lineup[slot.key];
                  return (
                    <SheetCard
                      key={slot.key}
                      slot={slot}
                      player={player}
                      active={picker.activeSlot === slot.key}
                      size="lg"
                      width={cardWidth}
                      points={cardPoints(slot.key)}
                      record={live && player ? recordThrough(liveEvent, player) : undefined}
                      out={cardOut(slot.key)}
                      replaced={replacedPick(slot.key)}
                      replacedPoints={replacedPickPoints(slot.key)}
                      onClick={() => selectCard(slot.key)}
                      onHover={(element) => (player ? handleHover(player, element) : undefined)}
                      onReplacedHover={handleHover}
                      onReplacedLongPress={openProfile}
                      onLongPress={player ? () => openProfile(player) : undefined}
                      onLeave={handleLeave}
                    />
                  );
                })}
              </div>
            </div>
            {live || !loginCta ? null : <div className="flex justify-center pb-3">{loginCta}</div>}
            <div className="flex flex-col items-center pt-3 border-t border-border">
              <ScoringRules />
            </div>
      </section>

      <section className="themed-scrollbar min-w-0 h-full overflow-y-auto [scrollbar-gutter:stable] px-7 pb-6">
        <div className={cn("sticky top-0 z-10 -mx-7 px-7 mb-3 bg-bg/95 backdrop-blur", showField && "border-b border-border")}>
          {viewTabs}
          {showField ? (
        <div className="py-3 flex items-center gap-4">
          <span className="shrink-0 grid text-[14px] text-subtle whitespace-nowrap">
            <span className="invisible col-start-1 row-start-1" aria-hidden="true">Picking Constructed</span>
            <span className="invisible col-start-1 row-start-1" aria-hidden="true">
              Replace before Round {liveEvent.cutRound + 1}
            </span>
            <span className="invisible col-start-1 row-start-1" aria-hidden="true">
              <DiscordIcon size={14} className="inline-block mr-1.5" />
              Log in to save picks
            </span>
            <span className="col-start-1 row-start-1">
              <PickingStatus picker={picker} phase={phase} signedIn={!loginCta} onSignIn={onSignIn} />
            </span>
          </span>
          <div className="flex-1 min-w-0 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
            <div className="w-max">
              <QualificationChips
                active={filters.qualification}
                onChange={filters.setQualification}
                players={liveEvent.players}
              />
            </div>
          </div>
          <SearchBox
            value={filters.search}
            onChange={filters.setSearch}
            placeholder="Search players"
            className="ml-auto w-[180px] shrink-0"
          />
        </div>
          ) : null}
        </div>
        <div className={showField ? undefined : "pt-3"}>{viewBody}</div>
      </section>

      {profileSheet}
      {hoverTarget ? (
        <HoverCard target={hoverTarget}>
          <PlayerProfile
            player={hoverTarget.player}
            compact
            preview
            event={profileEventFor(hoverTarget.player)}
          />
          <ProfileHint rightClick={clickPicks} />
        </HoverCard>
      ) : null}
    </main>
  );
}

function FieldGroups({
  picker,
  filters,
  compact,
  replacedSlotByName,
  onTileClick,
  onTileLongPress,
  onTileHover,
  onTileLeave,
}: {
  picker: Picker;
  filters: Filters;
  compact: boolean;
  replacedSlotByName: Map<string, SlotKey>;
  onTileClick: (player: FieldPlayer) => void;
  onTileLongPress: (player: FieldPlayer) => void;
  onTileHover: (player: FieldPlayer, element: HTMLElement) => void;
  onTileLeave: () => void;
}) {
  const liveEvent = useLiveEvent();
  const groups = useMemo(() => fieldGroups(filters.players), [filters.players]);

  const minColumn = compact ? 160 : 210;
  return (
    <div className={cn("flex flex-col", compact ? "gap-5" : "gap-7")}>
      {groups.map((group) => (
        <div key={group.key}>
          <SectionLabel size={compact ? 16 : 18} color="#ffffff" className={compact ? "mb-2" : "mb-3"}>
            {qualificationLabel(group.key, liveEvent.players).toUpperCase()}
          </SectionLabel>
          <div className={cn("grid", compact ? "gap-1.5" : "gap-2.5")} style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${minColumn}px, 1fr))` }}>
            {group.players.map((player) => (
              <FieldTile
                key={fullName(player)}
                player={player}
                pickedSlot={picker.pickedSlotByName.get(fullName(player)) ?? null}
                replacedSlot={replacedSlotByName.get(fullName(player)) ?? null}
                showSlotTag={!compact}
                out={isOut(liveEvent, player)}
                detail={
                  <span className="truncate">
                    {isOut(liveEvent, player) ? dayOneRecord(liveEvent, player) : player.country}
                  </span>
                }
                onClick={() => onTileClick(player)}
                onLongPress={() => onTileLongPress(player)}
                onHover={(element) => onTileHover(player, element)}
                onLeave={onTileLeave}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function fieldGroups(players: FieldPlayer[]): { key: Qualification; players: FieldPlayer[] }[] {
  const byQualification = new Map<Qualification, FieldPlayer[]>();
  for (const player of players) {
    const key = qualificationOf(player);
    const list = byQualification.get(key) ?? [];
    list.push(player);
    byQualification.set(key, list);
  }
  return QUALIFICATION_ORDER.filter((key) => byQualification.has(key)).map((key) => ({
    key,
    players: byQualification.get(key) ?? [],
  }));
}

function MobileTray({
  picker,
  cta,
  onOpenProfile,
  onSelect,
  cardPoints,
  cardOut,
  showSaved,
}: {
  picker: Picker;
  cta: ReactNode;
  showSaved: boolean;
  onOpenProfile: (player: FieldPlayer) => void;
  onSelect: (key: SlotKey) => void;
  cardPoints: (key: SlotKey) => number | undefined;
  cardOut: (key: SlotKey) => boolean;
}) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 bg-surface border-t border-border px-2 pt-1.5 pb-2">
      {cta ? (
        <div className="absolute left-1/2 bottom-full mb-3 -translate-x-1/2 drop-shadow-[0_6px_16px_rgba(0,0,0,0.6)]">{cta}</div>
      ) : showSaved ? (
        <SavedFlash lineup={picker.lineup} />
      ) : null}
      <div className="mx-auto grid grid-cols-4 gap-1.5" style={{ maxWidth: TRAY_MAX_WIDTH }}>
        {SLOTS.map((slot) => {
          const player = picker.lineup[slot.key];
          return (
            <SheetCard
              key={slot.key}
              slot={slot}
              player={player}
              active={picker.activeSlot === slot.key}
              size="xs"
              points={cardPoints(slot.key)}
              out={cardOut(slot.key)}
              onClick={() => {
                const alreadyReplacing = player && picker.activeSlot === slot.key;
                if (alreadyReplacing) {
                  picker.setActiveSlot(null);
                  return;
                }
                onSelect(slot.key);
              }}
              onLongPress={player ? () => onOpenProfile(player) : undefined}
            />
          );
        })}
      </div>
    </div>
  );
}

function LiveStatus({
  phase,
  roundsPlayed,
  score,
  rank,
  memberCount,
  short,
  spoilerControl,
}: {
  phase: EventPhase;
  roundsPlayed: number;
  spoilerControl: ReactNode;
  score: number;
  rank: number | null;
  memberCount: number;
  short: boolean;
}) {
  const { swissRounds, topEightStarted } = useLiveEvent();
  const quietStatus = phase === "top8" && topEightStarted ? undefined : QUIET_STATUS[phase];
  return (
    <span className="flex flex-col items-center text-center gap-1">
      <span className="flex items-baseline gap-x-6 gap-y-1 flex-wrap justify-center">
        {rank === null ? null : (
          <>
            <span className="flex items-baseline gap-1.5">
              <span className="font-num text-[18px] font-semibold text-green leading-none">{score}</span>
              <span className="text-[13px] text-subtle">pts</span>
            </span>
            <span className="text-[14px] text-text">
              Rank <b>{rank}</b> <span className="text-subtle">of {memberCount}</span>
            </span>
          </>
        )}
        <span className="inline-flex items-center gap-2 text-[13px] text-subtle">
          {quietStatus ? (
            quietStatus
          ) : (
            <>
              <LivePulse />
              {phase === "top8" ? "Top 8 Live" : `Round ${roundsPlayed + 1} of ${swissRounds}`}
            </>
          )}
          {spoilerControl}
        </span>
      </span>
      {short && phase === "cut" ? <CutNote /> : null}
    </span>
  );
}

function SpoilerEye({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  const [hover, setHover] = useState(false);
  const [tapToast, setTapToast] = useState(0);
  const Icon = on ? EyeOff : Eye;

  useEffect(() => {
    if (tapToast === 0) {
      return;
    }
    const timer = window.setTimeout(() => setTapToast(0), 2500);
    return () => window.clearTimeout(timer);
  }, [tapToast]);

  const showToastOnTap = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.pointerType !== "mouse") {
      setTapToast(Date.now());
    }
  };

  return (
    <Tooltip label={on ? SPOILER_FREE_TOOLTIP : SPOILERS_ON_TOOLTIP} side="bottom" open={hover || tapToast > 0}>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label="Spoiler free"
        onClick={onToggle}
        onPointerUp={showToastOnTap}
        onPointerEnter={(event) => event.pointerType === "mouse" && setHover(true)}
        onPointerLeave={() => setHover(false)}
        className="flex p-0.5 bg-transparent border-0 cursor-pointer text-subtle hover:text-text transition-colors"
      >
        <Icon size={16} />
      </button>
    </Tooltip>
  );
}

const SPOILER_FREE_TOOLTIP = (
  <>
    <span className="font-display text-[13px] tracking-[0.06em]">SPOILER FREE:</span> live coverage results only
  </>
);

const SPOILERS_ON_TOOLTIP = (
  <>
    <span className="font-display text-[13px] tracking-[0.06em]">SPOILERS ON:</span> latest results from melee.gg
  </>
);

const QUIET_STATUS: Partial<Record<EventPhase, string>> = {
  cut: "Day 1 complete",
  top8: "Top 8 plays Sunday",
  final: "Event complete",
};

function CutNote() {
  const { cutRound } = useLiveEvent();
  return (
    <span className="text-[13px] text-text">
      Replace players who missed <b>Day 2</b> before Round {cutRound + 1}
    </span>
  );
}

function LivePulse() {
  return <span className="h-2.5 w-2.5 self-center rounded-full bg-green animate-liveHalo" />;
}

function SavedFlash({ lineup }: { lineup: Picker["lineup"] }) {
  const [visible, setVisible] = useState(false);
  const lineupKey = SLOTS.map((slot) => (lineup[slot.key] ? fullName(lineup[slot.key] as FieldPlayer) : "")).join("|");
  const previousKey = useRef(lineupKey);

  useEffect(() => {
    if (previousKey.current === lineupKey) {
      return;
    }
    previousKey.current = lineupKey;
    setVisible(true);
    const timer = window.setTimeout(() => setVisible(false), 1400);
    return () => window.clearTimeout(timer);
  }, [lineupKey]);

  return (
    <span
      className={cn(
        "pointer-events-none absolute right-2 -top-8 flex items-center gap-1 rounded-full bg-surface border border-border2 px-2.5 py-1 text-[12px] text-green transition-opacity duration-300",
        visible ? "opacity-100" : "opacity-0",
      )}
    >
      <Check size={13} />
      Saved
    </span>
  );
}

function PickingStatus({
  picker,
  phase,
  signedIn,
  onSignIn,
}: {
  picker: Picker;
  phase: EventPhase;
  signedIn: boolean;
  onSignIn: () => void;
}) {
  const { cutRound } = useLiveEvent();
  if (phase === "day1" || phase === "day2" || phase === "top8" || phase === "final") {
    return (
      <>
        <Lock size={14} className="inline-block mr-1.5 align-[-2px]" />
        Picks are locked
      </>
    );
  }
  if (phase === "cut" && !picker.activeSlot) {
    return <>Replace before Round {cutRound + 1}</>;
  }
  if (!picker.activeSlot) {
    const complete = picker.filledCount === SLOTS.length;
    if (!complete) {
      return null;
    }
    if (!signedIn) {
      return (
        <button
          type="button"
          onClick={onSignIn}
          className="bg-transparent border-0 p-0 cursor-pointer text-green hover:underline text-[14px]"
        >
          <DiscordIcon size={14} className="inline-block align-[-2px] mr-1.5" />
          Log in to save picks
        </button>
      );
    }
    return (
      <>
        <Check size={14} className="inline-block align-[-2px] mr-1.5 text-green" />
        Picks saved
      </>
    );
  }
  const slot = slotFor(picker.activeSlot);
  return (
    <>
      Picking <span style={{ color: slot.accent }}>{slot.label}</span>
    </>
  );
}

const MOBILE_CREST_HEIGHT = 46;

function eventCrest(event: FantasyEventHeader, height: number): ReactNode {
  return event.crestUrl ? <EventCrest src={event.crestUrl} alt={event.crestAlt} height={height} /> : null;
}

function MobileHeader({ status }: { status: ReactNode }) {
  const fantasyEvent = useFantasyEvent();
  const [open, setOpen] = useState(true);
  return (
    <div className="px-3 pt-3 pb-3 bg-surface border-b border-border flex flex-col gap-2.5">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={open ? "Hide rules" : "Show rules"}
        className="relative grid w-full grid-cols-[1fr_auto_1fr] items-center gap-x-2 bg-transparent border-0 p-0 cursor-pointer"
      >
        <span />
        <span className="flex flex-col items-center min-w-0">
          <EventTitle
            event={fantasyEvent}
            crest={eventCrest(fantasyEvent, MOBILE_CREST_HEIGHT)}
            labelSize={12}
            glyphSize={26}
            titleSize={30}
            citySize={15}
          />
        </span>
        <span className="flex justify-end">
          <ChevronDown size={22} className={`text-subtle transition-transform ${open ? "" : "-rotate-90"}`} />
        </span>
      </button>
      <div className="flex flex-col items-center gap-0.5">
        {status ?? (
          <>
            <PicksPremise compact />
            <PicksCountdown size={13} />
          </>
        )}
      </div>
      {open ? <ScoringRules short /> : null}
    </div>
  );
}

function PicksPremise({ compact }: { compact: boolean }) {
  const { picksLockAt, shortName } = useFantasyEvent();
  const picksOpen = useNow(30_000) < picksLockAt.getTime();
  if (!picksOpen) {
    return null;
  }
  return (
    <p
      className={cn(
        "m-0 mb-2 text-center text-subtle",
        compact ? "text-[clamp(12px,3.45vw,13.5px)] leading-[1.5] whitespace-nowrap" : "text-[14px] leading-[1.55]",
      )}
    >
      Put together a team of four Pro Players from <span className="font-semibold text-text">{shortName}</span>
      <br />
      <span className="text-[max(12px,calc(1em-1px))]">You score points every time they win a match</span>
    </p>
  );
}

function ScoringRules({ short = false }: { short?: boolean }) {
  return (
    <div className="text-[14px] text-subtle leading-[1.6] text-center">
      <div>
        <b className="text-text">3 points</b> per match win and <b className="text-text">1</b> per draw
      </div>
      <div>
        <RoleName slotKey="captain" /> scores <b className="text-text">double</b> in All rounds
      </div>
      <div>
        <RoleName slotKey="drafter" /> scores <b className="text-text">triple</b> in Draft rounds
      </div>
      <div>
        <RoleName slotKey="constructed" /> scores <b className="text-text">double</b> in Constructed rounds
      </div>
      <div
        className={cn("mt-1.5", short && "whitespace-nowrap")}
        style={short ? { fontSize: "clamp(11px, 3.3vw, 14px)" } : undefined}
      >
        <DayTwoNote />
      </div>
      {short ? <div className="mt-1.5 italic">Press and hold a player for more details</div> : null}
    </div>
  );
}

function RoleName({ slotKey }: { slotKey: SlotKey }) {
  const slot = slotFor(slotKey);
  return <span className="font-semibold" style={{ color: slot.accent }}>{slot.label}</span>;
}

function DayTwoNote() {
  return (
    <>
      Players who miss <span className="font-semibold text-text">Day 2</span> can be replaced before Round 8
    </>
  );
}

const LARGE_CARD_WIDTH = 172;
const SMALLEST_CARD_WIDTH = 140;
const CARD_ASPECT = 63 / 88;
const TRAY_MAX_WIDTH = `calc(4 * 24svh * ${CARD_ASPECT} + 18px)`;
const CARD_AREA_CHROME = 24 + 16;
const CARD_NOTE_GAP = 20;

function useFittedCardWidth() {
  const cardAreaRef = useRef<HTMLDivElement>(null);
  const [cardWidth, setCardWidth] = useState(LARGE_CARD_WIDTH);
  useLayoutEffect(() => {
    const area = cardAreaRef.current?.parentElement;
    const cards = cardAreaRef.current;
    if (!area || !cards) {
      return;
    }
    const fit = () => {
      const cardNotes = cards.childElementCount - 1;
      let notesHeight = 0;
      for (const child of Array.from(cards.children).slice(0, cardNotes)) {
        notesHeight += (child as HTMLElement).offsetHeight + CARD_NOTE_GAP;
      }
      const restOfColumn = area.scrollHeight - cards.offsetHeight;
      const available = area.clientHeight - restOfColumn - notesHeight - CARD_AREA_CHROME;
      const fitted = Math.floor((available / 2) * CARD_ASPECT);
      setCardWidth(Math.max(SMALLEST_CARD_WIDTH, Math.min(LARGE_CARD_WIDTH, fitted)));
    };
    const observer = new ResizeObserver(fit);
    observer.observe(area);
    for (const child of Array.from(area.children)) {
      if (child !== cards) {
        observer.observe(child);
      }
    }
    fit();
    return () => observer.disconnect();
  }, []);
  const cardAreaMinHeight = Math.ceil((cardWidth / CARD_ASPECT) * 2) + CARD_AREA_CHROME;
  return { cardAreaRef, cardWidth, cardAreaMinHeight };
}

function SheetCard({
  slot,
  player,
  active,
  size,
  width = LARGE_CARD_WIDTH,
  onClick,
  onHover,
  onLeave,
  onLongPress,
  points,
  record,
  out = false,
  replaced,
  replacedPoints,
  labelSuffix,
  onReplacedHover,
  onReplacedLongPress,
}: {
  slot: Slot;
  player: FieldPlayer | undefined;
  active: boolean;
  size: "lg" | "xs";
  width?: number;
  points?: number;
  record?: string;
  out?: boolean;
  replaced?: FieldPlayer;
  replacedPoints?: number;
  labelSuffix?: string;
  onClick: () => void;
  onHover?: (element: HTMLElement) => void;
  onReplacedHover?: (player: FieldPlayer, element: HTMLElement) => void;
  onReplacedLongPress?: (player: FieldPlayer) => void;
  onLeave?: () => void;
  onLongPress?: () => void;
}) {
  const liveEvent = useLiveEvent();
  const tiny = size === "xs";
  const longPress = useLongPress(() => onLongPress?.());
  const frameColor = player || active ? slot.accent : `${slot.accent}55`;
  const cardWidth = tiny ? undefined : width;
  const card = (
    <button
      data-fantasy-pick-target
      type="button"
      onClick={() => {
        if (!longPress.consumeFired()) {
          onClick();
        }
      }}
      onMouseEnter={(event) => onHover?.(event.currentTarget)}
      onMouseLeave={onLeave}
      onTouchStart={onLongPress ? longPress.start : undefined}
      onTouchEnd={onLongPress ? longPress.cancel : undefined}
      onTouchMove={onLongPress ? longPress.cancel : undefined}
      onContextMenu={(event) => {
        event.preventDefault();
        onLongPress?.();
      }}
      className={cn(
        "relative flex flex-col border-0 text-left cursor-pointer transition-transform duration-150 hover:-translate-y-0.5 select-none [-webkit-touch-callout:none]",
        tiny ? "w-full p-[3px] rounded-[6px]" : "p-[5px] rounded-[9px]",
      )}
      style={{
        width: cardWidth,
        aspectRatio: "63 / 88",
        background: "#0a0c10",
        boxShadow: `inset 0 0 0 2px ${frameColor}${active ? `, 0 0 22px ${slot.accent}40` : ""}`,
      }}
    >
      <span className={cn("flex flex-col h-full overflow-hidden bg-surface2", tiny ? "rounded-[4px]" : "rounded-[5px]")}>
        {player ? (
          <span className={cn("flex items-center bg-surface", tiny ? "px-1.5 h-[22px]" : "px-2 h-[28px]")}>
            <FitText text={tiny ? shortLastName(player) : cardName(player)} maxSize={tiny ? 12 : 15} />
          </span>
        ) : null}
        <span className="relative flex-1 min-h-0 overflow-hidden">
          {player ? (
            <>
              <span className={cn("block w-full h-full transition-opacity", (active || out) && "opacity-30", out && "grayscale")}>
                <PlayerPortrait player={player} initialsSize={tiny ? 16 : 48} />
              </span>
              {out && !active && tiny ? (
                <span className="absolute inset-0 flex items-center justify-center px-1 text-center">
                  <span className="font-display tracking-[0.06em] text-text leading-none text-[18px]">
                    {dayOneRecord(liveEvent, player)}
                  </span>
                </span>
              ) : null}
              {record !== undefined && !tiny ? <CardStatPill className="left-1">{record}</CardStatPill> : null}
              {points !== undefined && !tiny ? <CardStatPill className="right-1">{points} pts</CardStatPill> : null}
              {points !== undefined && tiny ? (
                <span className="absolute right-1 bottom-1 rounded bg-black/80 px-1 py-0.5 font-num font-semibold leading-none text-[12px] text-text">
                  {points}
                  <span className="text-subtle font-normal"> pts</span>
                </span>
              ) : null}
              {active ? (
                <span className="absolute inset-0 flex flex-col items-center justify-center gap-1">
                  <Repeat size={tiny ? 20 : 30} strokeWidth={2} style={{ color: slot.accent }} />
                  <span
                    className={cn("font-display tracking-[0.12em]", tiny ? "text-[12px]" : "text-[15px]")}
                    style={{ color: slot.accent }}
                  >
                    REPLACE
                  </span>
                </span>
              ) : null}
            </>
          ) : (
            <span className="absolute inset-0 flex items-center justify-center">
              <Plus size={tiny ? 18 : 34} strokeWidth={1.5} style={{ color: active ? slot.accent : "#3b4458" }} />
            </span>
          )}
        </span>
        <span className={cn("bg-surface flex items-center justify-between gap-1", tiny ? "px-1.5 h-[22px]" : "px-2 h-[28px]")}>
          <span
            className={cn(
              "font-display whitespace-nowrap [text-box:trim-both_cap_alphabetic]",
              tiny ? "text-[13px] tracking-[0.06em]" : "text-[15px] tracking-[0.12em]",
            )}
            style={{ color: slot.accent }}
          >
            {labelSuffix ? `${slot.label.toUpperCase()} ${labelSuffix}` : slot.label.toUpperCase()}
          </span>
          {player && !tiny ? <CountryFlag code={player.countryCode} width={21} /> : null}
        </span>
      </span>
    </button>
  );
  if (!replaced || tiny) {
    return card;
  }
  return (
    <span className="relative inline-flex">
      <span className="absolute inset-0 translate-x-[10px] -translate-y-[10px] transition-transform duration-200 hover:z-[2] hover:translate-x-[16px] hover:-translate-y-[16px]">
        <SheetCard
          slot={slot}
          player={replaced}
          active={false}
          size="lg"
          width={width}
          points={replacedPoints}
          record={dayOneRecord(liveEvent, replaced)}
          labelSuffix={slot.key === "constructed" ? "D1" : "DAY 1"}
          out
          onClick={() => undefined}
          onHover={(element) => onReplacedHover?.(replaced, element)}
          onLongPress={() => onReplacedLongPress?.(replaced)}
          onLeave={onLeave}
        />
      </span>
      {card}
    </span>
  );
}

function CardStatPill({ className, children }: { className: string; children: ReactNode }) {
  return (
    <span
      className={cn(
        "absolute bottom-1 rounded bg-black/80 px-1.5 py-1 font-num font-semibold leading-none text-[15px] text-text",
        className,
      )}
    >
      {children}
    </span>
  );
}

const SHEET_VIEWS: SheetView[] = ["field", "standings", "top8", "leaderboard"];

const SHEET_VIEW_SLUG: Record<SheetView, string> = {
  field: "players",
  standings: "standings",
  top8: "top-8",
  leaderboard: "leaderboard",
};

function sheetViewFromSlug(slug: string | undefined): SheetView | undefined {
  for (const option of SHEET_VIEWS) {
    if (SHEET_VIEW_SLUG[option] === slug) {
      return option;
    }
  }
  return undefined;
}

const VIEW_LABEL: Record<SheetView, string> = {
  field: "PLAYERS",
  standings: "STANDINGS",
  top8: "TOP 8",
  leaderboard: "LEADERBOARD",
};

function ViewPlaceholder({
  title,
  detail,
  at,
  backdrop,
}: {
  title: string;
  detail: string;
  at?: ReactNode;
  backdrop?: ReactNode;
}) {
  return (
    <div className="relative">
      {backdrop ? (
        <div
          aria-hidden="true"
          className="pointer-events-none select-none opacity-50 [mask-image:linear-gradient(to_bottom,black_40%,transparent)]"
        >
          {backdrop}
        </div>
      ) : null}
      <div className={cn("flex justify-center", backdrop ? "absolute inset-x-0 top-16" : "py-16")}>
        <div
          className={cn(
            "max-w-[520px] flex flex-col items-center gap-2 text-center",
            backdrop && "mx-3 px-8 py-6 bg-surface border border-border2 shadow-2xl",
          )}
        >
          <span className="font-display text-[20px] tracking-[0.06em] text-text">{title.toUpperCase()}</span>
          <span className="text-[14px] text-subtle leading-[1.5]">{detail}</span>
          <span className="mt-1">{at}</span>
        </div>
      </div>
    </div>
  );
}

function defaultViewFor(phase: EventPhase): SheetView {
  if (phase === "top8") {
    return "top8";
  }
  if (phase === "final") {
    return "leaderboard";
  }
  return "field";
}
