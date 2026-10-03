import { fetchSetCardPool, isSetCode } from "../../../frontend/src/data/setCardPool";
import { serveStaleWhileRefreshing } from "../../_shared/stale-cache";

export const onRequestGet: PagesFunction = (context) => {
  const setCode = String(context.params.setCode ?? "").toUpperCase();
  if (!isSetCode(setCode)) {
    return new Response("Bad set code", { status: 400 });
  }
  const freshSeconds = 24 * 60 * 60;
  return serveStaleWhileRefreshing(context, `/api/set-cards/${setCode}`, freshSeconds, async () => {
    const pool = await fetchSetCardPool(setCode);
    return JSON.stringify(pool);
  });
};
