// Rares and mythics for a set, in Scryfall's set-review order. Same source and sort the
// tracker spreadsheet's grid builder uses, so the card order matches the old tabs.

export interface ColorSection {
  color: "W" | "U" | "B" | "R" | "G" | "M" | "C";
  label: string;
  cards: string[];
}

export interface SetCardLists {
  rares: ColorSection[];
  mythics: ColorSection[];
  /** Scryfall mana cost per card name, front face only for a double-faced card */
  costs: Record<string, string>;
}

const SECTION_ORDER: Array<ColorSection["color"]> = ["W", "U", "B", "R", "G", "M", "C"];
const SECTION_LABELS: Record<ColorSection["color"], string> = {
  W: "White", U: "Blue", B: "Black", R: "Red", G: "Green", M: "Multicolor", C: "Colorless",
};

interface ScryfallCard {
  name: string;
  rarity: string;
  color_identity?: string[];
  mana_cost?: string;
  card_faces?: Array<{ mana_cost?: string }>;
}

/** Color identity, not casting cost, so the sections match how Arena sorts a collection */
function sectionOf(card: ScryfallCard): ColorSection["color"] {
  const identity = card.color_identity ?? [];
  if (identity.length === 0) return "C";
  if (identity.length > 1) return "M";
  return identity[0] as ColorSection["color"];
}

function group(cards: ScryfallCard[]): ColorSection[] {
  const bySection = new Map<ColorSection["color"], string[]>();
  for (const card of cards) {
    const key = sectionOf(card);
    if (!bySection.has(key)) bySection.set(key, []);
    bySection.get(key)!.push(card.name);
  }
  const sections: ColorSection[] = [];
  for (const color of SECTION_ORDER) {
    const names = bySection.get(color);
    if (names?.length) sections.push({ color, label: SECTION_LABELS[color], cards: names });
  }
  return sections;
}

export async function fetchSetRaresAndMythics(setCode: string): Promise<SetCardLists> {
  const q = encodeURIComponent(`set:${setCode.toLowerCase()} (rarity:rare or rarity:mythic)`);
  let url: string | null = `https://api.scryfall.com/cards/search?q=${q}&unique=cards&order=review`;
  const cards: ScryfallCard[] = [];

  while (url) {
    const resp: Response = await fetch(url);
    if (!resp.ok) {
      if (resp.status === 404) return { rares: [], mythics: [], costs: {} };
      throw new Error(`Scryfall ${resp.status}`);
    }
    const page = await resp.json();
    cards.push(...(page.data as ScryfallCard[]));
    url = page.has_more ? (page.next_page as string) : null;
  }

  const costs: Record<string, string> = {};
  for (const card of cards) {
    const cost = card.mana_cost || card.card_faces?.[0]?.mana_cost;
    if (cost) {
      costs[card.name] = cost;
    }
  }

  return {
    rares: group(cards.filter((c) => c.rarity === "rare")),
    mythics: group(cards.filter((c) => c.rarity === "mythic")),
    costs,
  };
}
