import type { ReactNode } from "react";
import { AppHeader } from "../components/AppHeader";
import { Footer } from "../components/Footer";
import { ScoringExplainer } from "../components/ScoringExplainer";

const SEVENTEEN_LANDS_URL = "https://www.17lands.com";
const FEEDBACK_CHANNEL_URL = "https://discord.com/channels/775371722065051658/1504825374188507156";

export function AboutPage() {
  return (
    <div className="bg-bg text-text min-h-screen flex flex-col page-fade">
      <AppHeader subtitle="ABOUT" />
      <main className="flex-1 flex flex-col mx-auto w-full max-w-[1040px] px-5 md:px-10 pt-5 md:pt-10 pb-5 md:pb-5 md:relative">
        <Intro />
        <Rule />
        <ScoringExplainer />
        <Rule />
        <Feedback />
        <Footer className="mt-auto pt-3 md:mt-0 md:pt-0 md:absolute md:bottom-5 md:right-10" />
      </main>
    </div>
  );
}

function Intro() {
  return (
    <section>
      <SectionHeading>
        THE <span className="text-green">LEADERBOARD</span>
      </SectionHeading>
      <p className="text-[13px] md:text-[14px] text-muted leading-[1.6]">
        Ranks Discord members who opt in via <Cmd>/join</Cmd>, using their{" "}
        <ExternalLink href={SEVENTEEN_LANDS_URL}>17Lands</ExternalLink> data.
      </p>
      <p className="text-[13px] md:text-[14px] text-muted leading-[1.6] mt-2">
        Use <Cmd>/opt-out</Cmd> to hide your rank, keeping your profile and stats. Use <Cmd>/retire</Cmd>{" "}
        to hide everything until you come back.
      </p>
    </section>
  );
}

function Feedback() {
  return (
    <section>
      <SectionHeading>
        <span className="text-green">FEEDBACK</span>
      </SectionHeading>
      <p className="text-[13px] md:text-[14px] text-muted leading-[1.6]">
        Spotted a bug or have an idea to improve the site? Share it in{" "}
        <ExternalLink href={FEEDBACK_CHANNEL_URL}>#🤖-site-feedback</ExternalLink> channel on the Discord.
      </p>
    </section>
  );
}

function SectionHeading({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-display text-[16px] md:text-[18px] text-text tracking-[0.18em] mb-3 md:mb-4">
      {children}
    </h2>
  );
}

function Rule() {
  return (
    <div className="flex items-center gap-3 my-5 md:my-8" aria-hidden="true">
      <span className="w-1 h-1 bg-dim rotate-45 inline-block" />
      <span className="flex-1 h-px bg-border block" />
      <span className="w-1 h-1 bg-dim rotate-45 inline-block" />
    </div>
  );
}

function Cmd({ children }: { children: ReactNode }) {
  return (
    <code className="mono text-text bg-surface2 border border-border2 px-1.5 py-px text-[13px] whitespace-nowrap">
      {children}
    </code>
  );
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-green hover:underline underline-offset-2 whitespace-nowrap"
    >
      {children}
    </a>
  );
}
