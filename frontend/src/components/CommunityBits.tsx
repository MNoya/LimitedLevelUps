import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  BarChart3,
  BookOpen,
  GraduationCap,
  Layers,
  Leaf,
  ListOrdered,
  type LucideIcon,
  Mic,
  Package,
} from "lucide-react";
import { SiPatreon, SiTwitch, SiYoutube } from "react-icons/si";
import type { IconType } from "react-icons";
import { AAvatar } from "./Brand";
import { ChamferCta } from "./ChamferCta";
import { CATEGORY_COLOR } from "./CategoryTag";
import { SectionLabel } from "./SectionLabel";
import { ArrowRight, Globe } from "./Icons";
import { cn } from "../lib/utils";
import { categoryHref, COMMUNITY_SUPPORT_NOTE, COMMUNITY_SUPPORT_REWARDS, type CommunityLink } from "../data/community";
import { EPISODE_CATEGORIES, type EpisodeCategory } from "../data/episodes";
import { SITE_LINKS, type Host } from "../data/site";

export function CommunityHeading({ children }: { children: ReactNode }) {
  return (
    <SectionLabel size={22} letterSpacing="0.14em" className="text-text">
      {children}
    </SectionLabel>
  );
}

export function SectionPanel({
  title,
  watermark,
  children,
  className,
  bodyClassName,
}: {
  title: ReactNode;
  watermark?: GlyphIcon;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <PanelShell watermark={watermark} className={className}>
      <div className="relative flex flex-1 flex-col px-6 pt-6 pb-6">
        <PanelHeader title={title} />
        <div className={cn("relative flex-1 pt-5", bodyClassName)}>{children}</div>
      </div>
    </PanelShell>
  );
}

const CATEGORY_ICON: Record<EpisodeCategory, LucideIcon> = {
  "Set Review": BookOpen,
  Metagame: BarChart3,
  Draft: Layers,
  Sealed: Package,
  Rankings: ListOrdered,
  Coaching: GraduationCap,
  Guest: Mic,
  Evergreen: Leaf,
};

export function HostMug({ host, size = 88 }: { host: Host; size?: number }) {
  return <AAvatar displayName={host.name} avatarUrl={host.photo} size={size} green />;
}

const HOST_LINK_ICON: Record<string, IconType> = {
  Twitch: SiTwitch,
  YouTube: SiYoutube,
};

export function HostBlock({ host }: { host: Host }) {
  const twitter = host.links.find((link) => link.label === "Twitter");
  const otherLinks = host.links.filter((link) => link.label !== "Twitter");
  return (
    <div className="flex gap-4">
      <HostMug host={host} />
      <div className="min-w-0">
        <div className="flex items-center gap-3">
          <div className="font-display text-text text-[17px] tracking-[0.04em]">
            {host.name}{" "}
            {twitter ? (
              <a
                href={twitter.url}
                target="_blank"
                rel="noreferrer"
                aria-label={`${host.handle} on X`}
                className="text-muted no-underline transition-colors hover:text-green"
              >
                @{host.handle}
              </a>
            ) : (
              <span className="text-muted">{host.handle}</span>
            )}
          </div>
          <div className="flex items-center gap-2.5 shrink-0">
            {otherLinks.map((link) => {
              const Icon = HOST_LINK_ICON[link.label];
              return (
                <a
                  key={link.label}
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={link.label}
                  className="text-subtle transition-colors hover:text-green"
                >
                  {Icon ? <Icon size={16} /> : link.label}
                </a>
              );
            })}
          </div>
        </div>
        <div className="font-mono text-[11px] tracking-[0.12em] text-green uppercase mt-1">{host.role}</div>
        <p className="text-subtle text-[13.5px] leading-[1.6] mt-2">{host.bio}</p>
      </div>
    </div>
  );
}

const STEP_TOKEN = /(\/[a-z][\w-]*)|\[([^\]]+)\]\(([^)]+)\)/g;

function renderStep(step: string) {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  let match: RegExpExecArray | null;
  STEP_TOKEN.lastIndex = 0;
  while ((match = STEP_TOKEN.exec(step)) !== null) {
    if (match.index > cursor) {
      nodes.push(step.slice(cursor, match.index));
    }
    if (match[1]) {
      nodes.push(
        <code key={key++} className="font-mono text-text bg-surface2 border border-border2 px-1.5 py-px text-[12.5px]">
          {match[1]}
        </code>,
      );
    } else {
      nodes.push(
        <a
          key={key++}
          href={withProtocol(match[3])}
          target="_blank"
          rel="noreferrer"
          className="relative z-20 font-medium text-text no-underline transition-colors hover:text-green"
        >
          {match[2]}
        </a>,
      );
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < step.length) {
    nodes.push(step.slice(cursor));
  }
  return nodes;
}

function withProtocol(href: string) {
  if (/^https?:\/\//.test(href) || href.startsWith("/")) {
    return href;
  }
  return `https://${href}`;
}

export function EventCard({ event, className }: { event: CommunityLink; className?: string }) {
  return (
    <PanelShell
      watermark={event.Icon}
      watermarkClassName="opacity-30 transition-[opacity,color] duration-300 group-hover:opacity-100 group-hover:text-green/[0.14]"
      className={cn("transition-colors hover:border-green", className)}
    >
      <Link to={event.to} aria-label={event.cta} className="absolute inset-0 z-10" />
      <div className="relative flex flex-1 flex-col px-6 pt-6 pb-6">
        <div className="flex items-center gap-3">
          <event.Icon size={26} className="shrink-0 text-subtle transition-colors group-hover:text-green" />
          <span className="font-display text-text text-[26px] leading-[0.95] tracking-[0.03em] transition-colors group-hover:text-green">
            {event.title}
          </span>
        </div>
        <ul className="mt-4 flex flex-col gap-3">
          {event.steps.map((step) => (
            <li key={step} className="flex gap-3 text-subtle text-[13.5px] leading-[1.55]">
              <span className="mt-[7px] h-[5px] w-[5px] shrink-0 rotate-45 bg-green" />
              <span className="flex-1">{renderStep(step)}</span>
            </li>
          ))}
        </ul>
        <span className="mt-auto self-end pt-4 inline-flex items-center gap-1.5 whitespace-nowrap font-display text-[15px] tracking-[0.08em] text-green transition-colors group-hover:text-green-2">
          {event.cta}
          <ArrowRight size={15} />
        </span>
      </div>
    </PanelShell>
  );
}

type GlyphIcon = LucideIcon | IconType;

function PanelShell({
  watermark: Watermark,
  watermarkClassName,
  href,
  className,
  children,
}: {
  watermark?: GlyphIcon;
  watermarkClassName?: string;
  href?: string;
  className?: string;
  children: ReactNode;
}) {
  const shell = "group relative flex h-full flex-col overflow-hidden rounded-xl border border-border bg-surface";
  const content = (
    <>
      {Watermark ? (
        <Watermark
          size={120}
          className={cn(
            "pointer-events-none absolute right-8 top-6 text-border2/40 transition-colors duration-200",
            watermarkClassName,
          )}
        />
      ) : null}
      {children}
    </>
  );
  if (href) {
    return (
      <Link to={href} className={cn(shell, "no-underline transition-colors hover:border-green", className)}>
        {content}
      </Link>
    );
  }
  return <section className={cn(shell, className)}>{content}</section>;
}

function PanelHeader({ title }: { title: ReactNode }) {
  return <span className="font-display text-text text-[26px] leading-[0.95] tracking-[0.03em]">{title}</span>;
}

export function CommunityLinks() {
  const links = [
    { label: "Patreon", url: SITE_LINKS.patreon, icon: <SiPatreon size={18} /> },
    { label: "Podcast", url: SITE_LINKS.podcast, icon: <Globe size={18} strokeWidth={1.75} /> },
  ];
  return (
    <div className="flex flex-col max-w-[480px]">
      {links.map((link) => (
        <a
          key={link.label}
          href={link.url}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-3 md:gap-4 py-3 border-b border-border last:border-b-0 no-underline group transition-colors hover:bg-surface -mx-2 px-2"
        >
          <span className="text-subtle group-hover:text-green transition-colors shrink-0">{link.icon}</span>
          <span className="font-display text-[14px] md:text-[15px] tracking-[0.06em] text-text shrink-0 w-[90px]">
            {link.label}
          </span>
          <span className="font-mono text-[12px] md:text-[13px] text-muted group-hover:text-green transition-colors break-all">
            {displayUrl(link.url)}
          </span>
        </a>
      ))}
    </div>
  );
}

function displayUrl(url: string) {
  return url.replace(/^https?:\/\//, "");
}

export function SupportCard() {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
        <p className="text-subtle text-[13.5px] leading-[1.6]">{COMMUNITY_SUPPORT_NOTE}</p>
        <ChamferCta
          label="BECOME A PATRON"
          href={SITE_LINKS.patreon}
          target="_blank"
          className="shrink-0 self-center whitespace-nowrap sm:self-auto"
        />
      </div>
      <SupportRewards />
    </div>
  );
}

function SupportRewards() {
  return (
    <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
      {COMMUNITY_SUPPORT_REWARDS.map(({ Icon, label }) => (
        <span
          key={label}
          className="flex items-center justify-center gap-2 rounded-lg bg-surface2 px-3 py-2 sm:inline-flex sm:justify-start"
        >
          <Icon size={18} strokeWidth={2} className="shrink-0 text-green" />
          <span className="font-display uppercase tracking-[0.06em] text-[14.5px] text-text">{label}</span>
        </span>
      ))}
    </div>
  );
}

export function ShowTopics({
  topics,
}: {
  topics?: readonly { category: EpisodeCategory; label: string; Icon?: GlyphIcon; iconClassName?: string }[];
}) {
  const items: readonly { category: EpisodeCategory; label: string; Icon?: GlyphIcon; iconClassName?: string }[] =
    topics ?? EPISODE_CATEGORIES.map((category) => ({ category, label: category }));
  return (
    <div className="flex flex-wrap gap-2">
      {items.map(({ category, label, Icon: iconOverride, iconClassName }) => {
        const Icon = iconOverride ?? CATEGORY_ICON[category];
        return (
          <Link
            key={category}
            to={categoryHref(category)}
            className="group/chip inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-surface2 px-3 py-2 no-underline transition-all duration-200 hover:-translate-y-0.5 hover:bg-surface hover:ring-1 hover:ring-green/80 sm:flex-none sm:justify-start"
          >
            <Icon
              size={iconOverride ? 21 : 18}
              strokeWidth={iconOverride ? undefined : 2}
              className={cn(
                "shrink-0 transition-transform duration-200 group-hover/chip:scale-110",
                iconClassName ?? CATEGORY_COLOR[category],
              )}
            />
            <span className="whitespace-nowrap font-display uppercase tracking-[0.06em] text-[14.5px] text-text transition-colors group-hover/chip:text-green">
              {label}
            </span>
          </Link>
        );
      })}
    </div>
  );
}
