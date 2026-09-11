import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { cardImageSources, type CardImages } from "../data/cardImages";
import { preloadImage } from "../lib/imageReveal";
import { useIsMobile } from "../lib/use-is-mobile";
import { PREVIEW_W, PreviewShell, previewAnchorFor } from "./TierGrid";

type Anchor = ReturnType<typeof previewAnchorFor>;

const CARD_ASPECT = 680 / 488;
const PREVIEW_PADDING = 12;
const previewHeight = PREVIEW_W * CARD_ASPECT + PREVIEW_PADDING;

export function TranscriptCardLink({
  name,
  set,
  cardImages,
}: {
  name: string;
  set?: string;
  cardImages?: CardImages;
}) {
  const mobile = useIsMobile();
  const ref = useRef<HTMLButtonElement>(null);
  const hovering = useRef(false);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [sourceIndex, setSourceIndex] = useState(0);

  const sources = cardImageSources(name, set, cardImages);
  const src = sources[Math.min(sourceIndex, sources.length - 1)];
  const nextSource = () => setSourceIndex((i) => (i < sources.length - 1 ? i + 1 : i));

  useEffect(() => {
    if (mobile || !src || !ref.current) {
      return;
    }
    const element = ref.current;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          preloadImage(src);
          observer.disconnect();
        }
      },
      { rootMargin: "300px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [src, mobile]);

  const enterPreview = () => {
    hovering.current = true;
    if (!src) {
      return;
    }
    preloadImage(src, () => {
      if (hovering.current && ref.current) {
        setAnchor(previewAnchorFor(ref.current, previewHeight));
      }
    });
  };
  const leavePreview = () => {
    hovering.current = false;
    setAnchor(null);
  };

  useEffect(() => {
    if (!modalOpen) {
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setModalOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [modalOpen]);

  return (
    <>
      <button
        ref={ref}
        type="button"
        className="text-green underline decoration-green/40 underline-offset-2 transition-colors hover:decoration-green"
        onMouseEnter={mobile ? undefined : enterPreview}
        onMouseLeave={mobile ? undefined : leavePreview}
        onClick={mobile ? () => setModalOpen(true) : undefined}
      >
        {name}
      </button>
      {!mobile && anchor && src
        ? createPortal(
            <PreviewShell anchor={anchor}>
              <img
                src={src}
                alt={name}
                onError={nextSource}
                className="w-full rounded-[4.75%]"
                style={{ aspectRatio: "488 / 680" }}
              />
            </PreviewShell>,
            document.body,
          )
        : null}
      {modalOpen && src
        ? createPortal(
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6 backdrop-blur-sm animate-fadeIn"
              onClick={() => setModalOpen(false)}
              role="dialog"
              aria-modal="true"
            >
              <img
                src={src}
                alt={name}
                onError={nextSource}
                className="max-h-[85vh] w-auto rounded-2xl shadow-2xl"
                style={{ aspectRatio: "488 / 680" }}
              />
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
