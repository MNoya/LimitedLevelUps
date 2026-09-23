import { useState } from "react";

import { Trophy } from "../../Brand";
import { Record } from "../../Record";
import { cn } from "../../../lib/utils";
import type { PodCard } from "../../../data/podCards";
import {
  CardColorPairs,
  CardDeckList,
  CardImageStack,
  CoPlayedCards,
  PickCurve,
  useCardDetail,
  useCoPlayed,
  useDeckCycler,
  type CardDetail,
} from "./CardDetailParts";

export function CardDetailRow({
  boardCode,
  card,
  imageSources,
  artSources,
  season,
  search,
  colSpan,
  mobile = false,
}: {
  boardCode: string;
  card: PodCard;
  imageSources: string[];
  artSources: string[];
  season: string | null;
  search: string;
  colSpan: number;
  mobile?: boolean;
}) {
  const detail = useCardDetail(boardCode, card.name, season);
  const coPlayed = useCoPlayed(detail, card.name);
  const { openDeck, modal } = useDeckCycler(detail.decks);
  const { summary, isPending } = detail;

  const tally = <CardTally detail={detail} compact={mobile} />;
  const curve = (
    <PickCurve curve={summary.pickCurve} ata={card.ata} alsa={card.alsa} height={45} />
  );
  const colors = <CardColorPairs summary={summary} isPending={isPending} limit={6} reserveRows={!mobile} />;
  const decks = (
    <CardDeckList
      decks={detail.decks}
      isPending={isPending}
      onOpen={openDeck}
      pageSize={8}
      reserveRows={!mobile}
      hoverTips={!mobile}
      footerStart={mobile ? tally : undefined}
      className="min-w-0 h-full"
    />
  );
  const playedTogether = (limit: number, columns: number) => (
    <CoPlayedCards
      cards={coPlayed.cards}
      isPending={coPlayed.isPending}
      boardCode={boardCode}
      search={search}
      maindecks={summary.maindecks}
      limit={limit}
      columns={columns}
      reserveRows={!mobile}
    />
  );

  return (
    <tr>
      <td colSpan={colSpan} className="p-0 border-b border-border">
        <div
          className={cn(
            "relative bg-bg animate-fadeIn",
            mobile ? "sticky left-0 w-[100vw] px-4 py-5" : "px-5 py-5",
          )}
        >
          <ArtBackdrop sources={artSources} />
          {mobile ? (
            <div className="relative flex flex-col gap-4">
              {decks}
              {curve}
              {(isPending || summary.colorPairs.length > 0) && colors}
              {(coPlayed.isPending || coPlayed.cards.length > 0) && playedTogether(6, 2)}
            </div>
          ) : (
            <div
              className={cn(
                "relative grid items-stretch gap-x-6 gap-y-5",
                "grid-cols-[208px_minmax(240px,0.85fr)_minmax(0,1.3fr)]",
                "2xl:grid-cols-[232px_minmax(0,0.9fr)_minmax(0,1.3fr)_210px]",
              )}
            >
              <div className="-mb-5 flex flex-col">
                <CardImageStack sources={imageSources} />
                <div className="flex flex-1 items-center">{tally}</div>
              </div>
              <div className="min-w-0 flex flex-col justify-between gap-3">
                {colors}
                {curve}
              </div>
              {decks}
              <div className="hidden 2xl:block min-w-0">{playedTogether(7, 1)}</div>
            </div>
          )}
        </div>
        {modal}
      </td>
    </tr>
  );
}

function CardTally({ detail, compact }: { detail: CardDetail; compact: boolean }) {
  const { summary, isPending } = detail;
  const hasTrophies = summary.trophies > 0;
  return (
    <div
      className={cn(
        "flex items-center",
        compact ? "gap-7" : "w-full justify-between gap-4 px-3",
        isPending && "invisible",
      )}
    >
      <span className="flex items-center gap-1.5 font-num font-medium text-[15px] leading-none">
        <Trophy size={14} color={hasTrophies ? "#ffc63a" : undefined} className="text-dim" />
        <span className={hasTrophies ? "text-text" : "text-muted"}>{summary.trophies}</span>
      </span>
      <Record
        wins={summary.matchWins}
        losses={summary.matchLosses}
        className="font-num font-medium text-[15px] leading-none"
      />
    </div>
  );
}

function ArtBackdrop({ sources }: { sources: string[] }) {
  const [loaded, setLoaded] = useState(false);
  const src = sources[0];
  if (!src) {
    return null;
  }
  return (
    <img
      src={src}
      alt=""
      aria-hidden
      decoding="async"
      onLoad={() => setLoaded(true)}
      className={cn(
        "pointer-events-none absolute right-0 top-0 h-full w-[70%] object-cover transition-opacity duration-500",
        loaded ? "opacity-[0.16]" : "opacity-0",
      )}
      style={{
        maskImage: "linear-gradient(to right, transparent, black 60%)",
        WebkitMaskImage: "linear-gradient(to right, transparent, black 60%)",
      }}
    />
  );
}
