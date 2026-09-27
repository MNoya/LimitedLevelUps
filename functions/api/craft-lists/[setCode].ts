import { fetchCraftLists, isCraftSetCode } from "../../../frontend/src/data/craftListBuilder";
import { serveStaleWhileRefreshing } from "../../_shared/stale-cache";

export const onRequestGet: PagesFunction = (context) => {
  const setCode = String(context.params.setCode ?? "").toUpperCase();
  if (!isCraftSetCode(setCode)) {
    return new Response("Bad set code", { status: 400 });
  }
  const freshSeconds = 24 * 60 * 60;
  return serveStaleWhileRefreshing(context, `/api/craft-lists/${setCode}`, freshSeconds, async () => {
    const lists = await fetchCraftLists(setCode);
    return JSON.stringify(lists);
  });
};
