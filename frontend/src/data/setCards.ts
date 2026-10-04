import { useQuery } from "@tanstack/react-query";
import { isSetCode, type SetCardPool } from "./setCardPool";

export function useSetCardPool(setCode: string) {
  return useQuery({
    queryKey: ["set-cards", setCode],
    queryFn: () => fetchSetCards(setCode),
    staleTime: Infinity,
    enabled: isSetCode(setCode),
  });
}

async function fetchSetCards(setCode: string): Promise<SetCardPool> {
  const response = await fetch(`/api/set-cards/${setCode}`);
  if (!response.ok) {
    throw new Error(`Set cards failed with ${response.status}`);
  }
  return response.json();
}
