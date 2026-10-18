import { lazy, Suspense, useEffect } from "react";
import { Routes, Route, Navigate, useParams, useLocation } from "react-router-dom";
import { PLAYER_BASE } from "./data/utils";
import { Provider as TooltipProvider } from "@radix-ui/react-tooltip";
import { ScoringModalHost } from "./components/ScoringModal";
import { DocumentTitle } from "./components/DocumentTitle";
import { HomePage } from "./pages/HomePage";
import { EpisodesPage } from "./pages/EpisodesPage";
import { CommunityPage } from "./pages/CommunityPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { PlayerPage } from "./pages/PlayerPage";
import { PodDraftsPage, PodsRoute } from "./pages/PodDraftsPage";
import { PodGuidePage } from "./pages/PodGuidePage";
import { PodDraftLogRoute } from "./pages/PodPage";
import { AboutPage } from "./pages/AboutPage";
import { TierListPage } from "./pages/TierListPage";
import { PodCardDataPage } from "./pages/PodCardDataPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { P0P1Page } from "./pages/P0P1Page";
import { AppHeader } from "./components/AppHeader";
import { loadFantasyPage, loadFantasyReplayPage } from "./components/fantasy/proPlayChunks";
import { ProPlaySkeleton } from "./components/fantasy/ProPlaySkeleton";
import {
  proPlayHomeEvent,
  fantasyEventBySlug,
  fantasyEventPath,
  PRO_PLAY_BASE,
} from "./components/fantasy/fantasyEvents";
import { CraftToolPage } from "./pages/CraftToolPage";
import { ToolsPage } from "./pages/ToolsPage";
import { TrophyMageLabPage } from "./pages/TrophyMageLabPage";
import { WheelOfFortunePage } from "./pages/WheelOfFortunePage";
import { WheelQuickPage } from "./pages/WheelQuickPage";
import { WheelRevealMockupsPage } from "./pages/WheelRevealMockupsPage";
import { BannerLab } from "./pages/BannerLab";
import { preloadGuildLogos } from "./data/guild-art";

// Browser routes. The leaderboard is one section of the site, mounted at the
// lowercase /leaderboard; set codes stay uppercase under it.
//
//   /                → redirect to /leaderboard
//   /leaderboard     → leaderboard for the active set
//   /leaderboard/SOS → leaderboard for SOS
//   /player/x        → lifetime player profile
//   /player/x/SOS    → player profile (set-scoped)
//
// Legacy /leaderboard/[SOS/]player/x links redirect to the new /player paths.
// Archetype scoping happens via the inline picker on the leaderboard page,
// not as a separate route. Set codes are 2–4 uppercase letters.

export function App() {
  useEffect(() => {
    preloadGuildLogos();
  }, []);
  return (
    <TooltipProvider delayDuration={150} skipDelayDuration={0} disableHoverableContent>
      <DocumentTitle />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/episodes" element={<EpisodesPage />} />
        <Route path="/episodes/:categorySlug" element={<EpisodesPage />} />
        <Route path="/episodes/:categorySlug/:episodeSlug" element={<EpisodesPage />} />
        <Route path="/community" element={<CommunityPage />} />

        <Route path="/leaderboard" element={<LeaderboardPage />} />
        <Route path="/leaderboard/about" element={<AboutPage />} />
        <Route path="/leaderboard/:setCode" element={<LeaderboardPage />} />

        <Route path="/player/:slug" element={<PlayerPage />} />
        <Route path="/player/:slug/:setCode" element={<PlayerPage />} />
        <Route path="/player/:slug/:setCode/:trackerTab" element={<PlayerPage />} />
        <Route path="/leaderboard/player/:slug" element={<LegacyPlayerRedirect />} />
        <Route path="/leaderboard/:setCode/player/:slug" element={<LegacyPlayerRedirect />} />

        <Route path="/about" element={<Navigate to="/leaderboard/about" replace />} />
        <Route path="/players" element={<Navigate to="/leaderboard" replace />} />

        {/* Static /pods/guide ranks above /pods/:slug; declared first for readers */}
        <Route path="/pods/guide" element={<PodGuidePage />} />

        {/* Both render PodsRoute so moving between them reconciles instead of remounting the page */}
        <Route path="/pods" element={<PodsRoute />} />
        <Route path="/pods/:board/data" element={<PodCardDataPage />} />
        <Route path="/pods/:board/data/:card" element={<PodCardDataPage />} />
        <Route path="/pods/:slug" element={<PodsRoute />} />
        <Route path="/pods/:slug/:who" element={<PodDraftLogRoute />} />
        <Route path="/pods/:slug/:who/:pack/:pick" element={<PodDraftLogRoute />} />

        <Route
          path={PRO_PLAY_BASE}
          element={<Navigate to={fantasyEventPath(proPlayHomeEvent(new Date()))} replace />}
        />
        <Route path={`${PRO_PLAY_BASE}/:eventSlug`} element={<FantasyEventRoute />} />
        <Route path={`${PRO_PLAY_BASE}/:eventSlug/:view`} element={<FantasyEventRoute />} />
        <Route path="/tier-list" element={<TierListPage />} />
        <Route path="/tier-list/:setCode" element={<TierListPage />} />
        <Route path="/tier-list/:setCode/archetypes" element={<TierListPage skeletonsOpen />} />
        <Route path="/tier-list/:setCode/archetypes/:pair" element={<TierListPage skeletonsOpen />} />
        <Route path="/tier-list/:setCode/:card" element={<TierListPage />} />

        <Route path="/p0p1" element={<P0P1Page />} />
        <Route path="/p0p1/:setCode" element={<P0P1Page />} />

        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/tools/craft" element={<CraftToolPage />} />
        <Route path="/tools/craft/:setCode" element={<CraftToolPage />} />
        <Route path="/wheel-of-fortune" element={<WheelOfFortunePage />} />
        <Route path="/wheel-of-fortune/quick" element={<WheelQuickPage />} />
        <Route path="/wheel-of-fortune/:play" element={<WheelOfFortunePage />} />
        {import.meta.env.DEV && <Route path="/wheel-of-fortune/mockups" element={<WheelRevealMockupsPage />} />}
        <Route path="/tools/trophy-mage" element={<Navigate to="/trophy-mage" replace />} />
        <Route path="/trophy-mage" element={<TrophyMageLabPage />} />

        <Route path="/banner" element={<BannerLab />} />

        {/* Legacy archetype routes redirect to the leaderboard — the archetype
          picker now lives there inline. */}
        <Route path="/leaderboard/archetypes/*" element={<Navigate to="/leaderboard" replace />} />
        <Route path="/leaderboard/:setCode/archetypes/*" element={<Navigate to="/leaderboard" replace />} />

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <ScoringModalHost />
    </TooltipProvider>
  );
}

const FantasyPage = lazy(() => loadFantasyPage().then((module) => ({ default: module.FantasyPage })));
const FantasyReplayPage = lazy(() => loadFantasyReplayPage().then((module) => ({ default: module.FantasyReplayPage })));

const FantasyEventRoute = () => {
  const { eventSlug } = useParams();
  const event = fantasyEventBySlug(eventSlug);
  const teamSheet = Boolean(event && !event.replayOnly);
  const page = teamSheet && event ? <FantasyPage event={event} /> : <FantasyReplayPage />;
  return <Suspense fallback={<ProPlayLoading layout={teamSheet ? "sheet" : "replay"} />}>{page}</Suspense>;
};

const ProPlayLoading = ({ layout }: { layout: "sheet" | "replay" }) => (
  <div className="bg-bg text-text min-h-screen lg:h-screen lg:overflow-hidden flex flex-col">
    <AppHeader subtitle="Pro Play" fill />
    <ProPlaySkeleton layout={layout} />
  </div>
);

const LegacyPlayerRedirect = () => {
  const { slug, setCode } = useParams<{ slug: string; setCode?: string }>();
  const { search } = useLocation();
  const pathname = setCode ? `${PLAYER_BASE}/${slug}/${setCode}` : `${PLAYER_BASE}/${slug}`;
  return <Navigate to={{ pathname, search }} replace />;
};
