import { useMemo } from "react";
import { buildCraftLists } from "./craftListBuilder";
import { useSetCardPool } from "./setCards";

export {
  craftListLabel,
  craftListText,
  craftListTitle,
  craftListWildcards,
  type CraftList,
} from "./craftListBuilder";
export { isSetCode } from "./setCardPool";

export function useCraftLists(setCode: string) {
  const { data: pool, isPending, isError } = useSetCardPool(setCode);
  const lists = useMemo(() => (pool ? buildCraftLists(setCode, pool.cards) : []), [setCode, pool]);
  return { lists, isPending, isError };
}
