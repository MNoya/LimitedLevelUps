const FETCHED_AT = "x-fetched-at";

export const serveStaleWhileRefreshing = async (
  context: EventContext<unknown, string, unknown>,
  cachePath: string,
  freshSeconds: number,
  produceBody: (previous: Response | undefined) => Promise<string | null>,
): Promise<Response> => {
  const cacheKey = new Request(new URL(cachePath, context.request.url).toString());
  const hit = await caches.default.match(cacheKey);
  const refresh = () => storeFreshCopy(cacheKey, hit?.clone(), produceBody);

  if (hit) {
    const ageSeconds = (Date.now() - Number(hit.headers.get(FETCHED_AT) ?? 0)) / 1000;
    if (ageSeconds > freshSeconds) {
      context.waitUntil(refresh().catch(() => null));
    }
    return hit;
  }

  const fetched = await refresh().catch(() => null);
  return fetched ?? new Response("Upstream error", { status: 502 });
};

const storeFreshCopy = async (
  cacheKey: Request,
  previous: Response | undefined,
  produceBody: (previous: Response | undefined) => Promise<string | null>,
): Promise<Response | null> => {
  const body = await produceBody(previous);
  if (body === null) {
    return null;
  }
  const storedSeconds = 60 * 24 * 60 * 60;
  const response = new Response(body, {
    status: 200,
    headers: {
      "content-type": "application/json",
      "cache-control": `public, max-age=600, s-maxage=${storedSeconds}`,
      [FETCHED_AT]: String(Date.now()),
    },
  });
  await caches.default.put(cacheKey, response.clone());
  return response;
};
