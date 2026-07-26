import { SiDiscord, SiPatreon, SiYoutube } from "./Icons";

type IconProps = { size?: number; className?: string };

export function PatreonIcon({ size = 16, className }: IconProps) {
  return <SiPatreon size={size} className={className} aria-hidden />;
}

export function DiscordIcon({ size = 16, className }: IconProps) {
  return <SiDiscord size={size} className={className} aria-hidden />;
}

export function YoutubeIcon({ size = 16, className }: IconProps) {
  return <SiYoutube size={size} className={className} aria-hidden />;
}
