import type { TranscriptSegment } from "../data/transcript";

// Caption speaker-change markers (>>) are a display artifact; strip for reading and export.
export const stripSpeakerTurns = (text: string): string =>
  text
    .replace(/\s*>{2,}\s*/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();

export interface SpeakerTurn {
  lane: number;
  paragraphs: string[];
}

export function speakerTurns(priorSegments: TranscriptSegment[], segments: TranscriptSegment[]): SpeakerTurn[] {
  const speakerMarker = /\s*>{2,}\s*/;
  const speakerLanes = new Map<string, number>();
  const laneOfSpeaker = (speaker: string) => {
    if (!speakerLanes.has(speaker)) {
      speakerLanes.set(speaker, speakerLanes.size);
    }
    return speakerLanes.get(speaker)!;
  };
  let lane = 0;
  for (const segment of priorSegments) {
    if (segment.speaker) {
      laneOfSpeaker(segment.speaker);
    } else {
      lane = (lane + segment.text.split(speakerMarker).length - 1) % 2;
    }
  }
  const turns: SpeakerTurn[] = [];
  const addParagraph = (paragraphLane: number, text: string, continues: boolean) => {
    const last = turns[turns.length - 1];
    if (last && last.lane === paragraphLane && continues) {
      last.paragraphs.push(text);
    } else {
      turns.push({ lane: paragraphLane, paragraphs: [text] });
    }
  };
  for (const segment of segments) {
    if (segment.speaker) {
      addParagraph(laneOfSpeaker(segment.speaker), stripSpeakerTurns(segment.text), true);
      continue;
    }
    segment.text.split(speakerMarker).forEach((chunk, index) => {
      if (index > 0) {
        lane = 1 - lane;
      }
      const text = chunk.trim();
      if (text) {
        addParagraph(lane, text, index === 0);
      }
    });
  }
  return turns;
}

export function transcriptToText(title: string, segments: TranscriptSegment[]): string {
  const lines: string[] = [title];
  for (const segment of segments) {
    const text = stripSpeakerTurns(segment.text);
    if (segment.heading) {
      lines.push("", `# ${segment.heading}`, "", text);
    } else if (segment.subheading) {
      lines.push("", `## ${segment.subheading}`, "", text);
    } else {
      lines.push(text);
    }
  }
  return `${lines.join("\n").replace(/\n{3,}/g, "\n\n").trim()}\n`;
}

export function downloadTextFile(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
