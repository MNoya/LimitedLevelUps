export interface TranscriptSegment {
  t: number;
  text: string;
  heading?: string;
  subheading?: string;
  speaker?: string;
  cards?: { name: string }[];
}

export function transcriptWordCount(segments: TranscriptSegment[]): number {
  let count = 0;
  for (const segment of segments) {
    count += segment.text.split(/\s+/).filter(Boolean).length;
  }
  return count;
}
