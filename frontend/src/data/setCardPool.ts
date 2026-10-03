const SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search";
const NO_MATCHES_STATUS = 404;
const PAGE_DELAY_MS = 500;
const SPECIAL_GUESTS_SET = "spg";

export interface SetCard {
  name: string;
  layout: string;
  collectorNumber: string;
  rarity: string;
  colorIdentity: string[];
  manaCost: string | null;
  image: string | null;
}

export interface SetCardPool {
  cards: SetCard[];
  specialGuests: SetCard[];
}

interface ScryfallPrinting {
  name: string;
  set: string;
  collector_number: string;
  rarity: string;
  layout: string;
  type_line?: string;
  color_identity?: string[];
  mana_cost?: string;
  image_uris?: { normal?: string };
  card_faces?: Array<{ mana_cost?: string; image_uris?: { normal?: string } }>;
}

export function isSetCode(setCode: string): boolean {
  return /^[A-Z0-9]{2,5}$/.test(setCode);
}

export async function fetchSetCardPool(setCode: string): Promise<SetCardPool> {
  const code = setCode.toLowerCase();
  const printings = await scryfallSearch(`game:arena (set:${code} or (set:${SPECIAL_GUESTS_SET} date=${code}))`);
  const setPrintings = printings.filter((printing) => printing.set === code);
  if (setPrintings.length === 0) {
    return { cards: [], specialGuests: [] };
  }
  const guestPrintings = printings.filter((printing) => printing.set === SPECIAL_GUESTS_SET);
  return {
    cards: firstPrintingPerName(draftable(setPrintings)),
    specialGuests: firstPrintingPerName(guestPrintings),
  };
}

function draftable(printings: ScryfallPrinting[]): ScryfallPrinting[] {
  let firstBasic = Infinity;
  for (const printing of printings) {
    if (isBasicLand(printing)) {
      firstBasic = Math.min(firstBasic, collectorNumber(printing.collector_number));
    }
  }
  return printings.filter(
    (printing) => !isBasicLand(printing) && collectorNumber(printing.collector_number) < firstBasic,
  );
}

function isBasicLand(printing: ScryfallPrinting): boolean {
  const supertypes = (printing.type_line ?? "").split("—")[0];
  return supertypes.includes("Basic") && supertypes.includes("Land");
}

function firstPrintingPerName(printings: ScryfallPrinting[]): SetCard[] {
  const first = new Map<string, SetCard>();
  for (const printing of printings) {
    const card = toSetCard(printing);
    const current = first.get(card.name);
    if (!current || compareCollectorNumbers(card, current) < 0) {
      first.set(card.name, card);
    }
  }
  return [...first.values()];
}

export function compareCollectorNumbers(a: SetCard, b: SetCard): number {
  const byNumber = collectorNumber(a.collectorNumber) - collectorNumber(b.collectorNumber);
  if (byNumber !== 0) {
    return byNumber;
  }
  return a.collectorNumber.localeCompare(b.collectorNumber);
}

function toSetCard(printing: ScryfallPrinting): SetCard {
  const frontFace = printing.card_faces?.[0];
  return {
    name: printing.name,
    layout: printing.layout,
    collectorNumber: printing.collector_number,
    rarity: printing.rarity,
    colorIdentity: printing.color_identity ?? [],
    manaCost: printing.mana_cost || frontFace?.mana_cost || null,
    image: printing.image_uris?.normal ?? frontFace?.image_uris?.normal ?? null,
  };
}

function collectorNumber(value: string): number {
  const digits = value.match(/^\d+/);
  return digits ? Number(digits[0]) : Infinity;
}

async function scryfallSearch(query: string): Promise<ScryfallPrinting[]> {
  const params = new URLSearchParams({ q: query, unique: "prints", order: "review" });
  let url: string | null = `${SCRYFALL_SEARCH}?${params}`;
  const printings: ScryfallPrinting[] = [];
  while (url) {
    const response = await fetch(url, { headers: { accept: "application/json", "user-agent": "LimitedLevelUps/1.0" } });
    if (response.status === NO_MATCHES_STATUS) {
      return printings;
    }
    if (!response.ok) {
      throw new Error(`Scryfall search failed with ${response.status}`);
    }
    const page: { data: ScryfallPrinting[]; next_page?: string } = await response.json();
    printings.push(...page.data);
    url = page.next_page ?? null;
    if (url) {
      await new Promise((resolve) => setTimeout(resolve, PAGE_DELAY_MS));
    }
  }
  return printings;
}
