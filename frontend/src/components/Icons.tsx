import React from "react";
import {
  ArrowRight as LR_ArrowRight,
  ArrowUp as LR_ArrowUp,
  ChevronDown as LR_ChevronDown,
  ChevronLeft as LR_ChevronLeft,
  ChevronRight as LR_ChevronRight,
  ChevronsRight as LR_ChevronsRight,
  Clock as LR_Clock,
  ExternalLink as LR_ExternalLink,
  Globe as LR_Globe,
  Headphones as LR_Headphones,
  House as LR_House,
  Image as LR_Image,
  Info as LR_Info,
  Lock as LR_Lock,
  Music as LR_Music,
  RefreshCw as LR_RefreshCw,
  Rocket as LR_Rocket,
  CalendarRange as LR_CalendarRange,
  Trophy as LR_Trophy,
} from "lucide-react";
import { MdPause as R_MdPause, MdVideoLibrary as R_MdVideoLibrary } from "react-icons/md";
import { TbCards as R_TbCards, TbListNumbers as R_TbListNumbers } from "react-icons/tb";
import { LuScrollText as R_LuScrollText } from "react-icons/lu";
import { GiCardPick as R_GiCardPick, GiRoundTable as R_GiRoundTable } from "react-icons/gi";
import { GoSidebarCollapse as R_GoSidebarCollapse } from "react-icons/go";
import {
  BsAsterisk as R_BsAsterisk,
  BsPaletteFill as R_BsPaletteFill,
} from "react-icons/bs";
import {
  SiDiscord as R_SiDiscord,
  SiGithub as R_SiGithub,
  SiPatreon as R_SiPatreon,
  SiYoutube as R_SiYoutube,
} from "react-icons/si";

function withShrink<P extends { className?: string }>(
  Icon: React.ComponentType<P>,
): React.ComponentType<P> {
  return function ShrunkIcon(props: P) {
    const className = props.className ? `shrink-0 ${props.className}` : "shrink-0";
    return <Icon {...props} className={className} />;
  };
}

const _ArrowRight = withShrink(LR_ArrowRight);
export function ArrowRight(
  props: React.ComponentProps<typeof LR_ArrowRight>,
) {
  return <_ArrowRight strokeWidth={3} {...props} />;
}
export const ArrowUp = withShrink(LR_ArrowUp);
export const ChevronDown = withShrink(LR_ChevronDown);
export const ChevronLeft = withShrink(LR_ChevronLeft);
export const ChevronRight = withShrink(LR_ChevronRight);
export const ChevronsRight = withShrink(LR_ChevronsRight);
export const Clock = withShrink(LR_Clock);
export const Lock = withShrink(LR_Lock);
export const ExternalLink = withShrink(LR_ExternalLink);
export const Globe = withShrink(LR_Globe);
export const Headphones = withShrink(LR_Headphones);
export const House = withShrink(LR_House);
export const ImageIcon = withShrink(LR_Image);
export const Info = withShrink(LR_Info);
export const Music = withShrink(LR_Music);
export const RefreshCw = withShrink(LR_RefreshCw);
export const Rocket = withShrink(LR_Rocket);
export const Trophy = withShrink(LR_Trophy);
export const CalendarRange = withShrink(LR_CalendarRange);
export const Pause = withShrink(R_MdPause);
export function Play({ size = 24, className, ...rest }: { size?: number } & React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      className={className ? `shrink-0 ${className}` : "shrink-0"}
      {...rest}
    >
      <path d="M5 4.623V19.38a1.5 1.5 0 002.26 1.29L22 12 7.26 3.33A1.5 1.5 0 005 4.623Z" />
    </svg>
  );
}
export const MdVideoLibrary = withShrink(R_MdVideoLibrary);
export const TbCards = withShrink(R_TbCards);
export const TbListNumbers = withShrink(R_TbListNumbers);
export const LuScrollText = withShrink(R_LuScrollText);
export const GiCardPick = withShrink(R_GiCardPick);
export const GiRoundTable = withShrink(R_GiRoundTable);
export const GoSidebarCollapse = withShrink(R_GoSidebarCollapse);
export const BsAsterisk = withShrink(R_BsAsterisk);
export const BsPaletteFill = withShrink(R_BsPaletteFill);
export const SiDiscord = withShrink(R_SiDiscord);
export const SiGithub = withShrink(R_SiGithub);
export const SiPatreon = withShrink(R_SiPatreon);
export const SiYoutube = withShrink(R_SiYoutube);
