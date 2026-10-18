import { restGet } from "../../_shared/public-data";

export const onRequestGet: PagesFunction = async (context) => {
  const setCode = context.params.setCode;
  if (typeof setCode !== "string" || !/^[A-Za-z0-9]{2,8}$/.test(setCode)) {
    return new Response("Bad set code", { status: 400 });
  }
  const columns = "set_code,phase,date_start,date_end,cards";
  const query = `public_p0p1_ratings?select=${columns}&set_code=eq.${setCode.toUpperCase()}`;
  const upstream = await restGet(query, cacheSeconds);
  if (!upstream.ok) {
    return new Response("Upstream error", { status: 502 });
  }
  const cacheControl = upstream.headers.get("cache-control") ?? "no-store";
  const headers = { "content-type": "application/json", "cache-control": cacheControl };
  return new Response(upstream.body, { headers });
};

const cacheSeconds = (rows: unknown[]): number => {
  const hasFinal = rows.some((row) => (row as { phase?: string }).phase === "final");
  return hasFinal ? 365 * 24 * 60 * 60 : 60;
};
