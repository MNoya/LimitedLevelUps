import type { CardGroup } from "../../data/dailySealed";
import { BASICS_PILE_KEY } from "../../data/dailySealedLayout";
import type { BuilderView } from "../../pages/DailySealedPage";

export const deckGroupRows = (view: BuilderView): CardGroup[][] => {
  const { builder } = view;
  const basicsKey = BASICS_PILE_KEY[builder.sort.deck];
  const lastRow = builder.layout.deck.length - 1;
  return builder.layout.deck.map((row, rowIndex) => {
    const groups = row
      .map((pile) => ({
        key: pile.key,
        label: pile.key,
        entries: [
          ...pile.cards.map((index) => ({ index, card: view.pool.cards[index] })),
          ...(rowIndex === lastRow && pile.key === basicsKey ? view.basicCards : []),
        ],
      }))
      .filter((group) => group.entries.length > 0);
    const hasBasicsPile = row.some((pile) => pile.key === basicsKey);
    if (rowIndex !== lastRow || hasBasicsPile || view.basicCards.length === 0) {
      return groups;
    }
    const landGroup = { key: "land", label: "land", entries: view.basicCards };
    return builder.sort.deck === "mana" ? [landGroup, ...groups] : [...groups, landGroup];
  });
};
