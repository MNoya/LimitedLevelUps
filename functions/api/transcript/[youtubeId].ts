import { restPassthrough } from "../../_shared/public-data";

export const onRequestGet: PagesFunction = (context) => {
  const youtubeId = context.params.youtubeId;
  if (typeof youtubeId !== "string" || !/^[\w-]{1,64}$/.test(youtubeId)) {
    return new Response("Bad transcript key", { status: 400 });
  }
  return restPassthrough(`public_episode_transcripts?select=segments&youtube_id=eq.${youtubeId}`, 60 * 60);
};
