import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { isScryfallSyntax, isSetCode, normalizeScryfallQuery } from "./setCardPool";
import { cardNameKey } from "./tierList";

export type ScryfallMatches = { kind: "name" } | { kind: "searching" } | { kind: "found"; names: Set<string> };

export function useScryfallNameMatches(setCode: string | undefined, text: string): ScryfallMatches {
  const query = isScryfallSyntax(text) ? normalizeScryfallQuery(text) : "";
  const settled = useSettledValue(query);
  const { data, isError } = useQuery({
    queryKey: ["card-search", setCode, settled],
    queryFn: () => fetchCardSearch(setCode!, settled),
    enabled: Boolean(setCode && isSetCode(setCode.toUpperCase()) && settled),
    staleTime: Infinity,
  });
  if (!query) {
    return { kind: "name" };
  }
  if (isError) {
    return { kind: "found", names: new Set() };
  }
  if (settled !== query || data === undefined) {
    return { kind: "searching" };
  }
  return { kind: "found", names: new Set(data.map(cardNameKey)) };
}

function useSettledValue(value: string): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), 400);
    return () => clearTimeout(timer);
  }, [value]);
  return settled;
}

async function fetchCardSearch(setCode: string, query: string): Promise<string[]> {
  const params = new URLSearchParams({ q: query });
  const response = await fetch(`/api/card-search/${setCode.toUpperCase()}?${params}`);
  if (!response.ok) {
    throw new Error(`Card search failed with ${response.status}`);
  }
  return response.json();
}
