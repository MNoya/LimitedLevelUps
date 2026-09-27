// Proxies 17lands' tier-list endpoint, which lacks CORS headers; in dev a vite proxy entry serves the same path
import { TIER_LIST_GRADERS } from "../../../frontend/src/data/constants";
import { serveStaleWhileRefreshing } from "../../_shared/stale-cache";

export const onRequestGet: PagesFunction = (context) => {
  const uid = context.params.uid;
  if (typeof uid !== "string" || !/^[0-9a-f]{32}$/.test(uid)) {
    return new Response("Bad uid", { status: 400 });
  }

  const graderUids = Object.values(TIER_LIST_GRADERS).flatMap((graders) => graders.map((g) => g.uid));
  const freshSeconds = graderUids.includes(uid) ? 30 * 24 * 60 * 60 : 10 * 60;
  return serveStaleWhileRefreshing(context, `/api/tier-list/${uid}`, freshSeconds, async () => {
    const upstream = await fetch(`https://www.17lands.com/data/tier_list/${uid}`, {
      headers: { accept: "application/json" },
    });
    return upstream.ok ? upstream.text() : null;
  });
};
