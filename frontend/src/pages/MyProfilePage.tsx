import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { AppHeader } from "../components/AppHeader";
import { DiscordIcon } from "../components/BrandIcons";
import { Cmd } from "../components/Cmd";
import { CtaPill } from "../components/CtaPill";
import { Footer } from "../components/Footer";
import { useMyProfilePath } from "../data/hooks";
import { SITE_LINKS } from "../data/site";

export function MyProfilePage() {
  const { user, loading, signIn } = useAuth();
  const { path, resolving, failed } = useMyProfilePath(user?.discordId);
  if (path) {
    return <Navigate to={path} replace />;
  }
  if (loading || resolving) {
    return <ProfileShell />;
  }
  if (failed) {
    return (
      <ProfileShell>
        <ProfileMessage title="YOUR PROFILE" text="Could not load your profile. Refresh to try again" />
      </ProfileShell>
    );
  }
  if (!user) {
    return (
      <ProfileShell>
        <ProfileMessage title="YOUR PROFILE" text="Log in with Discord to see your trophies, drafts and stats" />
        <button type="button" onClick={signIn} className="bg-transparent border-0 p-0 cursor-pointer">
          <CtaPill size="md">LOG IN</CtaPill>
        </button>
      </ProfileShell>
    );
  }
  return (
    <ProfileShell>
      <ProfileMessage
        title="NO PROFILE YET"
        text={
          <>
            Run <Cmd>/join</Cmd> in the LLU Discord to link your 17lands account
          </>
        }
      />
      <a href={SITE_LINKS.discord} target="_blank" rel="noopener noreferrer" className="no-underline">
        <CtaPill size="md" icon={<DiscordIcon size={17} />}>
          OPEN DISCORD
        </CtaPill>
      </a>
    </ProfileShell>
  );
}

function ProfileShell({ children }: { children?: ReactNode }) {
  return (
    <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
      <AppHeader subtitle="" />
      <main className="flex-1 flex flex-col items-center justify-center text-center px-5 gap-6 md:gap-7">
        {children}
      </main>
      <Footer className="px-5 md:px-10 pb-5" />
    </div>
  );
}

function ProfileMessage({ title, text }: { title: string; text: ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <h1 className="font-display text-green leading-none tracking-[0.1em] text-[44px] md:text-[68px]">{title}</h1>
      <p className="text-text text-[14px] md:text-[15px] leading-[1.6]">{text}</p>
    </div>
  );
}
