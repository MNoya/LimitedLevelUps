import { forwardRef, useImperativeHandle, useRef, useState, type CSSProperties } from "react";

import { Pause, Play } from "./Icons";
import { PlayBadge } from "./PlayBadge";
import { cn } from "../lib/utils";

export interface AudioControls {
  seek: (seconds: number) => void;
}

export const PodcastAudioPlayer = forwardRef<AudioControls, { src: string; title: string }>((
  { src, title },
  controlsRef,
) => {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(true);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

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
  };

  useImperativeHandle(controlsRef, () => ({ seek }), []);

  const ratio = duration > 0 ? current / duration : 0;

  return (
    <div className="absolute inset-0">
      <audio
        ref={audioRef}
        src={src}
        autoPlay
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
      />
      <button
        type="button"
        onClick={togglePlay}
        aria-label={playing ? `Pause ${title}` : `Play ${title}`}
        className="group/audio absolute inset-0 w-full cursor-pointer"
      >
        <span
          className={cn(
            "absolute inset-0 flex items-center justify-center bg-bg/30 transition-opacity",
            playing ? "opacity-0 group-hover/audio:opacity-100" : "opacity-100",
          )}
        >
          <PlayBadge>
            {playing ? <Pause size={28} /> : <Play size={32} />}
          </PlayBadge>
        </span>
      </button>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 p-3 bg-gradient-to-t from-bg via-bg/90 to-transparent">
        <div className="flex items-center gap-2.5">
          <Equalizer playing={playing} />
          <span className="mono text-[11px] text-text tabular-nums shrink-0">{formatClock(current)}</span>
          <input
            type="range"
            className="audio-scrubber pointer-events-auto flex-1 min-w-0"
            min={0}
            max={duration || 0}
            step="any"
            value={current}
            onChange={(e) => seek(Number(e.target.value))}
            aria-label="Seek"
            style={{ "--pct": ratio } as CSSProperties}
          />
          <span className="mono text-[11px] text-muted tabular-nums shrink-0">{formatClock(duration)}</span>
        </div>
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
