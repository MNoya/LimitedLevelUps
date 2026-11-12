import { useMemo } from "react";
import { buildCraftLists, type CraftCopies } from "./craftListBuilder";
import { useSetCardPool } from "./setCards";

export {
  craftListLabel,
  craftListText,
  craftListTitle,
  craftListWildcards,
  type CraftCopies,
  type CraftList,
  type CraftRarity,
} from "./craftListBuilder";
export { isSetCode } from "./setCardPool";

export function useCraftLists(setCode: string, copies: CraftCopies) {
  const { data: pool, isPending, isError } = useSetCardPool(setCode);
  const lists = useMemo(() => (pool ? buildCraftLists(setCode, pool, copies) : []), [setCode, pool, copies]);
  return { lists, isPending, isError };
}
