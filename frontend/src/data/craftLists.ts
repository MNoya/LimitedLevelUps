import { useQuery } from "@tanstack/react-query";
import { isCraftSetCode, type CraftList } from "./craftListBuilder";

export {
  craftListLabel,
  craftListText,
  craftListTitle,
  craftListWildcards,
  isCraftSetCode,
  type CraftList,
} from "./craftListBuilder";

export function useCraftLists(setCode: string) {
  return useQuery({
    queryKey: ["craft-lists", setCode],
    queryFn: () => fetchCraftLists(setCode),
    staleTime: Infinity,
    retry: false,
    enabled: isCraftSetCode(setCode),
  });
}

async function fetchCraftLists(setCode: string): Promise<CraftList[]> {
  const response = await fetch(`/api/craft-lists/${setCode}`);
  if (!response.ok) {
    throw new Error(`Craft lists failed with ${response.status}`);
  }
  return response.json();
}
