import { restGet } from "../_shared/public-data";

export const onRequestGet: PagesFunction = async () => {
  const oneHour = 60 * 60;
  const upstream = await restGet("public_sets?select=*&order=start_date.desc", oneHour);
  if (!upstream.ok) {
    return new Response("Upstream error", { status: 502 });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "content-type": "application/json",
      "cache-control": `public, max-age=${oneHour}`,
    },
  });
};
