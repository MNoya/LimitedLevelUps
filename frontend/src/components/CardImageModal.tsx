import { useEffect } from "react";
import { createPortal } from "react-dom";

export function CardImageModal({
  src, alt, onError, onClose,
}: { src: string; alt: string; onError: () => void; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6 backdrop-blur-sm animate-fadeIn"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <img
        src={src}
        alt={alt}
        onError={onError}
        className="max-h-[85vh] w-auto rounded-2xl shadow-2xl"
        style={{ aspectRatio: "488 / 680" }}
      />
    </div>,
    document.body,
  );
}
