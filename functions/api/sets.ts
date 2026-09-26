import { restGet } from "../_shared/public-data";

export const onRequestGet: PagesFunction = async (context) => {
  const cache = caches.default;
  const cacheKey = new Request(new URL("/api/sets", context.request.url).toString());
  const hit = await cache.match(cacheKey);
  if (hit) {
    return hit;
  }

  const oneHour = 60 * 60;
  const upstream = await restGet("public_sets?select=*&order=start_date.desc", oneHour);
  if (!upstream.ok) {
    return new Response("Upstream error", { status: 502 });
  }

  const response = new Response(upstream.body, {
    status: 200,
    headers: {
      "content-type": "application/json",
      "cache-control": `public, max-age=${oneHour}`,
    },
  });
  context.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
};
