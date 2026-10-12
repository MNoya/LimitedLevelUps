import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AppHeader } from "../components/AppHeader";
import { EventReplay, REPLAY_VIEW_SLUG, type ReplayView } from "../components/fantasy/EventReplay";
import { fantasyEventBySlug } from "../components/fantasy/fantasyEvents";
import { hasReplay, loadReplay } from "../components/fantasy/fantasyReplay";
import { NotFoundPage } from "./NotFoundPage";
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
  });

  useLockedViewport();

  if (!replayable || !view) {
    return <NotFoundPage />;
  }
  return (
    <div className="bg-bg text-text min-h-screen lg:h-screen lg:overflow-hidden flex flex-col page-fade">
      <AppHeader subtitle="Pro Play" fill />
      {replay ? <EventReplay replay={replay} view={view} /> : null}
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
