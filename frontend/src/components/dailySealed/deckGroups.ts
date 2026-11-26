import type { CardGroup } from "../../data/dailySealed";
import { BASICS_PILE_KEY, basicsColumnAt, basicsRow } from "../../data/dailySealedLayout";
import type { BuilderView } from "../../pages/DailySealedPage";

export const deckGroupRows = (view: BuilderView): CardGroup[][] => {
  const { builder, basicCards } = view;
  const sort = builder.sort.deck;
  const basicsKey = BASICS_PILE_KEY[sort];
  const landsRow = basicsRow(builder.layout);
  return builder.layout.deck.map((row, rowIndex) => {
    const inLandsRow = rowIndex === landsRow;
    const groups: CardGroup[] = row.map((pile) => ({
      key: pile.key,
      label: pile.key,
      entries: [
        ...pile.cards.map((index) => ({ index, card: view.pool.cards[index] })),
        ...(inLandsRow && pile.key === basicsKey ? basicCards : []),
      ],
    }));
    if (inLandsRow && basicCards.length > 0 && !row.some((pile) => pile.key === basicsKey)) {
      const at = basicsColumnAt(builder.layout, sort, row.length);
      groups.splice(at, 0, { key: "land", label: "land", entries: basicCards });
    }
    return groups.filter((group) => group.entries.length > 0);
  });
};
