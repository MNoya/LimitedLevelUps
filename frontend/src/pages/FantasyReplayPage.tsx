import { useParams } from "react-router-dom";
import { useEffect } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AppHeader } from "../components/AppHeader";
import { EventReplay, REPLAY_VIEW_SLUG, type ReplayView } from "../components/fantasy/EventReplay";
import { fantasyEventBySlug } from "../components/fantasy/fantasyEvents";
import { hasReplay, loadReplay } from "../components/fantasy/fantasyReplay";
import { NotFoundPage } from "./NotFoundPage";
import { ProPlaySkeleton } from "../components/fantasy/ProPlaySkeleton";
import { prefetchProPlay } from "../components/fantasy/proPlayChunks";
import { LoadingEventHeader } from "../components/fantasy/FantasyParts";
import { DevStatePanel } from "../components/DevStatePanel";
import { useIsMobile } from "../lib/use-is-mobile";
import { LOADING_PRESETS, setFantasyDevPreset, useFantasyDevPreset } from "../components/fantasy/fantasyDevState";
import { useLockedViewport } from "../lib/use-locked-viewport";

export function FantasyReplayPage() {
  const { eventSlug, view: viewSlug } = useParams();
  const event = fantasyEventBySlug(eventSlug);
  const view = viewFromSlug(viewSlug);
  const replayable = Boolean(event && hasReplay(event) && view);
  const { data: replay } = useQuery({
    queryKey: ["fantasy-replay", event?.code],
    queryFn: () => loadReplay(event!),
    enabled: replayable,
    staleTime: Infinity,
    placeholderData: keepPreviousData,
  });

  useLockedViewport();
  useEffect(prefetchProPlay, []);
  const devPreset = useFantasyDevPreset(event);
  const isMobile = useIsMobile(1024);

  if (!replayable || !view) {
    return <NotFoundPage />;
  }
  return (
    <div className="bg-bg text-text min-h-screen lg:h-screen lg:overflow-hidden flex flex-col page-fade">
      <AppHeader subtitle="Pro Play" fill />
      {replay && devPreset !== "skeleton" ? (
        <EventReplay replay={replay} view={view} />
      ) : (
        <ProPlaySkeleton
          layout="replay"
          header={event ? <LoadingEventHeader event={event} compact={isMobile} layout="replay" /> : undefined}
        />
      )}
      <DevStatePanel
        title="DEV - PRO PLAY STATE"
        options={LOADING_PRESETS}
        value={devPreset === "skeleton" ? devPreset : "live"}
        onChange={setFantasyDevPreset}
        liveValue="live"
      />
    </div>
  );
}

function viewFromSlug(slug: string | undefined): ReplayView | undefined {
  for (const [view, viewSlug] of Object.entries(REPLAY_VIEW_SLUG)) {
    if (viewSlug === slug) {
      return view as ReplayView;
    }
  }
  return undefined;
}
