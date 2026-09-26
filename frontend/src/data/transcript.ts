export interface TranscriptSegment {
  t: number;
  text: string;
  heading?: string;
  subheading?: string;
  speaker?: string;
  cards?: { name: string }[];
}

export interface SetReviewMention {
  youtubeId: string;
  title: string;
  segmentIndex: number;
  t: number;
}

export type SetReviewMentions = Map<string, SetReviewMention>;

export const setReviewMentionKey = (cardName: string): string => cardName.split(" // ")[0].toLowerCase();

export function cardDiscussion(
  segments: TranscriptSegment[],
  startIndex: number,
  cardName: string,
  maxSegments = 14,
): TranscriptSegment[] {
  const ownKey = setReviewMentionKey(cardName);
  const discussion: TranscriptSegment[] = [];
  for (let index = startIndex; index < segments.length && discussion.length < maxSegments; index += 1) {
    const segment = segments[index];
    if (index > startIndex && opensAnotherCard(segment, ownKey)) {
      break;
    }
    discussion.push(segment);
  }
  return discussion;
}

function opensAnotherCard(segment: TranscriptSegment, ownKey: string): boolean {
  if (segment.heading) {
    return true;
  }
  if (!segment.subheading) {
    return false;
  }
  for (const card of segment.cards ?? []) {
    if (setReviewMentionKey(card.name) !== ownKey) {
      return true;
    }
  }
  return false;
}

export function transcriptWordCount(segments: TranscriptSegment[]): number {
  let count = 0;
  for (const segment of segments) {
    count += segment.text.split(/\s+/).filter(Boolean).length;
  }
  return count;
}
