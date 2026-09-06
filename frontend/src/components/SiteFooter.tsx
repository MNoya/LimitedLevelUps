import type { IconType } from "react-icons";
import { SiApplepodcasts, SiPatreon, SiRss, SiSpotify } from "react-icons/si";
import { FaYoutube } from "react-icons/fa";
import { LISTEN_ON, SITE_LINKS } from "../data/site";
import { TcgPlayerLogo } from "./TcgPlayerLogo";
import { cn } from "../lib/utils";

const FOOTER_ICONS: Record<string, IconType> = {
  Apple: SiApplepodcasts,
  Spotify: SiSpotify,
  YouTube: FaYoutube,
  RSS: SiRss,
  Patreon: SiPatreon,
};

const SPONSOR_HREF = SITE_LINKS.tcgplayer;
const SPONSOR_IMG = { color: "/sponsors/tcgplayer-stacked-offwhite.png" };
const SPONSOR_IMG_HOVER = "/sponsors/tcgplayer-stacked-hover.png";

export function SiteFooter({ sponsorVariant = "gray" }: { sponsorVariant?: "color" | "gray" }) {
  const links = [...LISTEN_ON, { label: "Patreon", url: SITE_LINKS.patreon }];
  const linkByLabel = Object.fromEntries(links.map((link) => [link.label, link]));
  const renderLink = ({ label, url }: { label: string; url: string }) => {
    const Icon = FOOTER_ICONS[label];
    return (
      <a
        key={label}
        href={url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 no-underline hover:text-green transition-colors"
      >
        {Icon ? <Icon className="text-[16px]" /> : null}
        {label}
      </a>
    );
  };
  const copyright = (
    <>
      <span>© Limited Level-Ups is unofficial Fan Content permitted under the Fan Content Policy.</span>{" "}
      <span>Not approved or endorsed by Wizards. Portions © Wizards of the Coast.</span>
    </>
  );
  const sponsorLogo = (heightClass: string, anchorClass = "") => {
    if (sponsorVariant === "gray") {
      return (
        <a
          rel="sponsored"
          href={SPONSOR_HREF}
          target="_blank"
          aria-label="TCGplayer"
          className={cn("inline-flex shrink-0 text-muted hover:text-green transition-colors", anchorClass)}
        >
          <TcgPlayerLogo className={heightClass} />
        </a>
      );
    }
    return (
      <a
        rel="sponsored"
        href={SPONSOR_HREF}
        target="_blank"
        aria-label="TCGplayer"
        className={cn("group relative inline-block shrink-0", anchorClass)}
      >
        <img
          src={SPONSOR_IMG.color}
          alt="TCGplayer"
          width={477}
          height={200}
          className={cn("block w-auto max-w-none", heightClass)}
        />
        <img
          src={SPONSOR_IMG_HOVER}
          alt=""
          aria-hidden
          width={477}
          height={200}
          className={cn(
            "pointer-events-none absolute left-0 top-0 hidden w-auto max-w-none group-hover:block",
            heightClass,
          )}
        />
      </a>
    );
  };
  const desktopHeight = sponsorVariant === "color" ? "h-9" : "h-5";
  const mobileHeight = sponsorVariant === "color" ? "h-7" : "h-[15px]";
  const navClass = "flex items-center justify-center gap-5 font-display tracking-[0.12em] text-[15px]";
  const row = (
    <>
      <div className="relative hidden items-center justify-between text-[12px] text-muted lg:flex">
        <span className="mono flex flex-col gap-0.5 text-[10px] leading-tight">{copyright}</span>
        <div className="pointer-events-none absolute inset-0 grid grid-cols-[minmax(300px,360px)_minmax(0,1fr)_clamp(300px,22vw,340px)] items-center gap-4">
          {sponsorLogo(desktopHeight, "pointer-events-auto col-start-2 justify-self-center")}
        </div>
        <nav className={navClass}>{links.map(renderLink)}</nav>
      </div>
      <div className="flex flex-col items-center gap-3 text-[11px] text-muted lg:hidden">
        <nav className="grid grid-cols-3 items-center justify-items-start gap-x-5 gap-y-3.5 font-display tracking-[0.12em] text-[15px]">
          {renderLink(linkByLabel.YouTube)}
          {sponsorLogo(mobileHeight, "justify-self-center")}
          {renderLink(linkByLabel.Patreon)}
          {renderLink(linkByLabel.Apple)}
          {renderLink(linkByLabel.Spotify)}
          {renderLink(linkByLabel.RSS)}
        </nav>
        <span className="mono block text-center text-[10px] leading-tight">{copyright}</span>
      </div>
    </>
  );
  return (
    <footer className="border-t border-border">
      <div className="px-4 lg:px-5 py-3">{row}</div>
    </footer>
  );
}
