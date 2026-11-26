const IMAGE_HOST = "https://cards.17landscapes.com";
const ONE_YEAR_SECONDS = 31536000;

export const onRequestGet: PagesFunction = async (context) => {
  const path = [context.params.path ?? []].flat().join("/");
  const search = new URL(context.request.url).search;
  const upstream = await fetch(`${IMAGE_HOST}/${path}${search}`, {
    cf: { cacheEverything: true, cacheTtl: ONE_YEAR_SECONDS },
  });
  if (!upstream.ok) {
    return new Response(null, { status: upstream.status });
  }
  return new Response(upstream.body, {
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "image/webp",
      "cache-control": `public, max-age=${ONE_YEAR_SECONDS}, immutable`,
    },
  });
};
