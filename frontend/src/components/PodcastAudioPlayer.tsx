import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type CSSProperties } from "react";

import { Pause, Play } from "./Icons";
import { EpisodeThumbnail } from "./EpisodeThumbnail";
import { cn } from "../lib/utils";

export interface AudioControls {
  seek: (seconds: number) => void;
}

export const PodcastAudioPlayer = forwardRef<
  AudioControls,
  { src: string; title: string; image?: string | null; pending?: boolean; onTime?: (seconds: number) => void }
>(({ src, title, image, pending, onTime }, controlsRef) => {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) {
      return;
    }
    void el.play().catch(() => setPlaying(false));
  }, [src]);

  const togglePlay = () => {
    const el = audioRef.current;
    if (!el) {
      return;
    }
    if (el.paused) {
      el.play();
    } else {
      el.pause();
    }
  };

  const seek = (seconds: number) => {
    const el = audioRef.current;
    if (!el) {
      return;
    }
    el.currentTime = seconds;
    setCurrent(seconds);
    onTime?.(seconds);
  };

  useImperativeHandle(controlsRef, () => ({ seek }), []);

  const ratio = duration > 0 ? current / duration : 0;
  return (
    <div className="flex items-center gap-3 border border-border bg-surface p-2.5">
      <audio
        ref={audioRef}
        src={src}
        autoPlay
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => {
          setCurrent(e.currentTarget.currentTime);
          onTime?.(e.currentTarget.currentTime);
        }}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
      />
      <button
        type="button"
        onClick={togglePlay}
        aria-label={playing ? `Pause ${title}` : `Play ${title}`}
        className="group/art relative h-16 w-16 shrink-0 cursor-pointer overflow-hidden border border-border bg-surface2"
      >
        <EpisodeThumbnail src={image ?? undefined} pending={pending} />
        <span className="absolute inset-0 flex items-center justify-center bg-bg/25 transition-colors group-hover/art:bg-bg/40">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-green/85 text-white transition-colors group-hover/art:bg-green">
            {playing ? <Pause size={16} /> : <Play size={18} />}
          </span>
        </span>
      </button>
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        <Equalizer playing={playing} />
        <span className="font-num text-[11px] text-text tabular-nums shrink-0">{formatClock(current)}</span>
        <input
          type="range"
          className="audio-scrubber flex-1 min-w-0"
          min={0}
          max={duration || 0}
          step="any"
          value={current}
          onChange={(e) => seek(Number(e.target.value))}
          aria-label="Seek"
          style={{ "--pct": ratio } as CSSProperties}
        />
        <span className="font-num text-[11px] text-muted tabular-nums shrink-0">{formatClock(duration)}</span>
      </div>
    </div>
  );
});

PodcastAudioPlayer.displayName = "PodcastAudioPlayer";

function Equalizer({ playing }: { playing: boolean }) {
  return (
    <span className="flex items-end gap-0.5 h-3.5 w-[13px] shrink-0" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={cn("w-[3px] h-full origin-bottom bg-green transition-opacity", playing ? "opacity-100" : "opacity-40")}
          style={playing ? { animation: `eqBar 0.9s ease-in-out ${i * 0.18}s infinite` } : { transform: "scaleY(0.4)" }}
        />
      ))}
    </span>
  );
}

function formatClock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return "0:00";
  }
  const whole = Math.floor(seconds);
  const s = String(whole % 60).padStart(2, "0");
  const m = Math.floor(whole / 60) % 60;
  const h = Math.floor(whole / 3600);
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}
