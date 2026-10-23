import { createContext, useContext, type MouseEvent } from "react";
import { Link, type LinkProps } from "react-router-dom";

import { OPENED_IN_APP } from "../../lib/modal-history";
import { isPlainClick } from "../../lib/plain-click";
import type { DeckTab } from "./DeckScreenshotModal";

export interface SeatRef {
  playerSlug: string | null;
  seatIndex: number | null;
}

export interface InPlaceLink {
  href: string;
  open: () => void;
}

const PodPagePathContext = createContext<{ slug: string; path: string } | null>(null);

export const PodPagePathProvider = PodPagePathContext.Provider;

export const podPagePath = (slug: string) => `/pods/${slug}`;

export const usePodPagePath = (slug: string) => {
  const hosted = useContext(PodPagePathContext);
  return hosted?.slug === slug ? hosted.path : podPagePath(slug);
};

export const podSeatHref = (pagePath: string, seatName: string | null) =>
  podPageHref(pagePath, seatName, null, "screenshot");

export const podDeckHref = (
  pagePath: string,
  seatName: string | null,
  ownerName: string,
  view: DeckTab = "screenshot",
) => podPageHref(pagePath, seatName, ownerName, view);

export const podDraftLogHref = (slug: string, seat: SeatRef) => `/pods/${slug}/${seatIdentifier(seat)}`;

export const podDraftPickHref = (slug: string, seat: SeatRef, pack: number, pick: number) =>
  `${podDraftLogHref(slug, seat)}/${pack + 1}/${pick + 1}`;

export const onPlainClick = (action: (() => void) | undefined) => {
  if (!action) {
    return undefined;
  }
  return (event: MouseEvent) => {
    if (!isPlainClick(event)) {
      return;
    }
    event.preventDefault();
    action();
  };
};

export const DeckLink = (props: LinkProps) => <Link state={OPENED_IN_APP} {...props} />;

const podPageHref = (pagePath: string, seatName: string | null, deckOwnerName: string | null, view: DeckTab) => {
  const params = new URLSearchParams();
  if (seatName) {
    params.set("player", seatName);
  }
  if (deckOwnerName) {
    params.set("deck", deckOwnerName);
    if (view === "decklist") {
      params.set("view", "pool");
    }
  }
  const query = params.toString();
  return query ? `${pagePath}?${query}` : pagePath;
};

const seatIdentifier = (seat: SeatRef) => seat.playerSlug ?? String(seat.seatIndex);
