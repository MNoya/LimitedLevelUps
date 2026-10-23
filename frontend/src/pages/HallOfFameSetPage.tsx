import { useMemo } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { BackButton, MobilePageHeader } from "../components/PageNav";
import { ChampionshipTabs, ChampionshipTitle, UPCOMING_TABS } from "../components/hallOfFame/ChampionshipChrome";
import { PlayerProfileCard } from "../components/hallOfFame/PlayerProfileCard";
import { QualificationList } from "../components/hallOfFame/QualificationList";
import { useChampionshipEvent, useChampionshipPlayers } from "../components/hallOfFame/useChampionship";
import { useChampionshipField } from "../components/hallOfFame/useChampionshipField";
import { usePodCalendar } from "../data/hooks";
import { useIsMobile } from "../lib/use-is-mobile";
import {
  championshipViewFromSegment,
  championshipViewHref,
  HALL_OF_FAME_PATH,
  hallOfFameSetHref,
  type ChampionshipView,
} from "../data/setChampionship";
import { PodPage } from "./PodPage";

const UPCOMING_LABEL = "👑 SET CHAMPIONSHIP";

export function HallOfFameSetPage() {
  const params = useParams();
  const setCode = (params.setCode ?? "").toUpperCase();
  const view = championshipViewFromSegment(params.view);
  const { event, isLoading } = useChampionshipEvent(setCode);
  if (!view) {
    return <Navigate to={hallOfFameSetHref(setCode)} replace />;
  }
  const started = event !== undefined && (event.isFinalized || new Date(event.eventTime).getTime() <= Date.now());
  if (event && started) {
    return <PodPage slugOverride={event.slug} championshipView={view} />;
  }
  if (isLoading) {
    return null;
  }
  if (view === "bracket") {
    return <Navigate to={hallOfFameSetHref(setCode)} replace />;
  }
  return <UpcomingChampionship setCode={setCode} view={view} />;
}

function UpcomingChampionship({ setCode, view }: { setCode: string; view: ChampionshipView }) {
  const navigate = useNavigate();
  const location = useLocation();
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
      })),
    [field.seats],
  );
  const { players, statsLoading } = useChampionshipPlayers(setCode, identities);
  const switchView = (next: ChampionshipView) => navigate(`${championshipViewHref(setCode, next)}${location.search}`);

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

  if (isMobile) {
    return (
      <div className="bg-bg text-text min-h-screen flex flex-col">
        <MobilePageHeader backTo={HALL_OF_FAME_PATH} prevTo={null} nextTo={null} />
        <ChampionshipTabs tabs={UPCOMING_TABS} view={view} onChange={switchView} className="w-full" />
        <div className="px-3 py-4">{content}</div>
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
              <ChampionshipTitle setCode={setCode} label={UPCOMING_LABEL} day={day} />
            </span>
          </span>
          <ChampionshipTabs tabs={UPCOMING_TABS} view={view} onChange={switchView} />
          <span />
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto themed-scrollbar py-4">
          <div className={view === "top8" ? "w-full" : "w-full max-w-[860px] mx-auto"}>{content}</div>
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
