import { useMemo, type CSSProperties } from "react";

import { useFallbackImage } from "./pod/review/ReviewCard";
import { useImageReveal } from "../lib/imageReveal";
import { cn } from "../lib/utils";

export function RevealImage({
  sources,
  alt = "",
  className,
  style,
}: {
  sources: string[];
  alt?: string;
  className?: string;
  style?: CSSProperties;
}) {
  const signature = sources.join("|");
  const stableSources = useMemo(() => signature.split("|").filter(Boolean), [signature]);
  const { src, onError } = useFallbackImage(stableSources);
  const { loaded, instant, onLoad } = useImageReveal(src ?? "");
  return (
    <div className={cn("relative overflow-hidden bg-surface2", className)} style={style}>
      {!loaded && <div className="absolute inset-0 animate-pulse bg-surface2" />}
      {src && (
        <img
          key={src}
          src={src}
          alt={alt}
          loading="lazy"
          decoding="async"
          onLoad={onLoad}
          onError={onError}
          className={cn(
            "block h-full w-full object-cover",
            loaded ? "opacity-100" : "opacity-0",
            !instant && "transition-opacity duration-300",
          )}
        />
      )}
    </div>
  );
}
