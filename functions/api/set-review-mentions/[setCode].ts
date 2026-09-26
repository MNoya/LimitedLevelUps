import { restPassthrough } from "../../_shared/public-data";

export const onRequestGet: PagesFunction = (context) => {
  const setCode = context.params.setCode;
  if (typeof setCode !== "string" || !/^[\w-]{1,16}$/.test(setCode)) {
    return new Response("Bad set code", { status: 400 });
  }
  const columns = "card_name,youtube_id,title,segment_index,t";
  return restPassthrough(`public_set_review_card_mentions?select=${columns}&set_code=eq.${setCode}`, 60 * 60);
};
