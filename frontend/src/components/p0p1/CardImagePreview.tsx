import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { preloadImage } from "../../lib/imageReveal";

interface Props {
  imageUrl: string;
  alt: string;
  children: ReactNode;
  className?: string;
}

export function CardImagePreview({ imageUrl, alt, children, className }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <div
        className={`relative shrink-0 cursor-pointer ${className ?? ""}`}
        onClick={(e) => {
          e.stopPropagation();
          preloadImage(imageUrl, () => setOpen(true));
        }}
      >
        {children}
      </div>
      {open ? <CardZoomOverlay imageUrl={imageUrl} alt={alt} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

export function CardZoomOverlay({ imageUrl, alt, onClose }: { imageUrl: string; alt: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 p-6"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div className="w-full max-w-[320px] overflow-hidden rounded-xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <img src={imageUrl} alt={alt} className="w-full block rounded-xl" />
      </div>
    </div>,
    document.body,
  );
}
