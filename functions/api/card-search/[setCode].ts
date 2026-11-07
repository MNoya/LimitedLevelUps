import { isSetCode, normalizeScryfallQuery, searchSetCardNames } from "../../../frontend/src/data/setCardPool";
import { serveStaleWhileRefreshing } from "../../_shared/stale-cache";

export const onRequestGet: PagesFunction = (context) => {
  const setCode = String(context.params.setCode ?? "").toUpperCase();
  const query = normalizeScryfallQuery(new URL(context.request.url).searchParams.get("q") ?? "");
  if (!isSetCode(setCode) || !query) {
    return new Response("Bad set code or query", { status: 400 });
  }
  const cachePath = `/api/card-search/${setCode}?${new URLSearchParams({ q: query.toLowerCase() })}`;
  const freshSeconds = 24 * 60 * 60;
  return serveStaleWhileRefreshing(context, cachePath, freshSeconds, async () => {
    return JSON.stringify(await searchSetCardNames(setCode, query));
  });
};
