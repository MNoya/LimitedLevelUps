import { useEffect } from "react";
import { AppHeader } from "../components/AppHeader";
import { CtaPill } from "../components/CtaPill";
import { DiscordIcon } from "../components/BrandIcons";
import { TeamSheet } from "../components/fantasy/TeamSheet";
import { prefetchProPlay } from "../components/fantasy/proPlayChunks";
import { DevStatePanel } from "../components/DevStatePanel";
import { devToolsEnabled } from "../lib/dev-preset-store";
import {
  DEMO_PRESETS,
  demoPresetsAllowed,
  FANTASY_DEV_PRESETS,
  setFantasyDevPreset,
  useFantasyDevPreset,
} from "../components/fantasy/fantasyDevState";
import { useAuth } from "../auth/useAuth";
import { useLockedViewport } from "../lib/use-locked-viewport";
import {
  FantasyEventContext,
  fantasyEventHeader,
  type FantasyEventEntry,
} from "../components/fantasy/fantasyEvents";

export function FantasyPage({ event }: { event: FantasyEventEntry }) {
  const { user, loading: authLoading, signIn } = useAuth();

  useLockedViewport();
  useEffect(prefetchProPlay, []);

  const devPreset = useFantasyDevPreset(event);
  const signedOut = devPreset === "pickingLoggedOut" || (!authLoading && !user);

  const loginCta = signedOut ? (
    <button type="button" onClick={signIn} className="bg-transparent border-0 cursor-pointer p-0">
      <CtaPill size="sm" icon={<DiscordIcon size={15} />}>LOG IN TO PICK</CtaPill>
    </button>
  ) : null;

  return (
    <div className="bg-bg text-text min-h-screen lg:h-screen lg:overflow-hidden flex flex-col page-fade">
      <AppHeader subtitle="Pro Play" fill />
      <FantasyEventContext.Provider value={fantasyEventHeader(event)}>
        <TeamSheet loginCta={loginCta} onSignIn={signIn} />
      </FantasyEventContext.Provider>
      <DevStatePanel
        title={devToolsEnabled ? "DEV - PRO PLAY STATE" : "DEMO - PRO PLAY"}
        label={devToolsEnabled ? "DEV" : "DEMO"}
        enabled={demoPresetsAllowed(event)}
        options={devToolsEnabled ? FANTASY_DEV_PRESETS : DEMO_PRESETS}
        value={devPreset}
        onChange={setFantasyDevPreset}
        liveValue="live"
      />
    </div>
  );
}
