import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { Check, Copy, Download, Share2, X } from "lucide-react";
import { toBlob } from "html-to-image";

import { SetGlyph } from "../Brand";
import { Pips } from "../ManaPips";
import { cn } from "../../lib/utils";
import type { CardGroup } from "../../data/dailySealed";
import type { BuilderView } from "../../pages/DailySealedPage";
import { chipClass } from "../pod/review/reviewControls";
import { ColumnRow } from "./cards";
import { deckGroupRows } from "./deckGroups";
import { formatDay, GREEN_CTA } from "./shared";
import { useCopyFeedback } from "../CopyTextButton";
import { useHeight, useWidth } from "./cardWidth";
import { useIsMobile } from "../../lib/use-is-mobile";

const IMAGE_CARD_WIDTH = 140;
const CARD_IMAGE_HOST = "https://cards.17landscapes.com/";
const HANKEN_GROTESK_CSS = "https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700&display=swap";
const MANA_FONT = "https://cdn.jsdelivr.net/npm/mana-font@latest/fonts/mana.woff";
const ARENA_ICON = `${import.meta.env.BASE_URL}platforms/mtga.png`;

export const ShareDeckModal = ({ view, onClose }: { view: BuilderView; onClose: () => void }) => {
  const stageRef = useRef<HTMLDivElement>(null);
  const imageKey = shareImageKey(view);
  const [blob, setBlob] = useState<Blob | null>(() => builtImages.get(imageKey) ?? null);
  const [wasBuilt] = useState(() => builtImages.has(imageKey));
  const [imageShown, setImageShown] = useState(false);
  const [sweptOnce, setSweptOnce] = useState(false);
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const fileName = `daily-sealed-${view.pool.setCode.toLowerCase()}-${view.pool.poolNumber}.png`;
  const file = useMemo(() => (blob ? new File([blob], fileName, { type: "image/png" }) : null), [blob, fileName]);
  const canShare = useMemo(() => canShareFiles(), []);
  const canCopy = typeof ClipboardItem !== "undefined" && !!navigator.clipboard?.write;
  const pretendCopy = import.meta.env.DEV && !canCopy;
  const blobReady = useRef(deferredBlob());
  const overlayRef = useRef<HTMLDivElement>(null);
  const narrow = useIsMobile();
  const overlayAndPanelPadding = narrow ? 26 : 58;
  const frameWidth = useWidth(overlayRef) - overlayAndPanelPadding;
  const stageWidth = useWidth(stageRef);
  const stageHeight = useHeight(stageRef);
  const scale =
    frameWidth > 0 && stageWidth > 0 && stageHeight > 0
      ? Math.min(1, frameWidth / stageWidth, (window.innerHeight * (narrow ? 0.75 : 0.7)) / stageHeight)
      : 0;
  const arenaCopy = useCopyFeedback();

  useEffect(() => {
    if (canCopy) {
      navigator.clipboard
        .write([new ClipboardItem({ "image/png": blobReady.current.promise })])
        .then(() => setCopied(true), () => undefined);
    } else if (pretendCopy) {
      blobReady.current.promise.then(() => setCopied(true), () => undefined);
    }
  }, []);
  useEffect(() => {
    if (failed) {
      blobReady.current.reject(new Error("The share image didn't build"));
    }
  }, [failed]);
  useEffect(() => {
    if (!blob) {
      return;
    }
    blobReady.current.resolve(blob);
    const url = URL.createObjectURL(blob);
    setImageUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blob]);
  useEffect(() => {
    const node = stageRef.current;
    if (!node || wasBuilt) {
      return;
    }
    let cancelled = false;
    buildShareImage(node, imageKey)
      .then((result) => {
        if (!cancelled) {
          result ? setBlob(result) : setFailed(true);
        }
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    const oneSweepMs = 1400;
    const timer = window.setTimeout(() => setSweptOnce(true), oneSweepMs);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const copy = async () => {
    if (!blob) {
      return;
    }
    if (pretendCopy) {
      setCopied(true);
      return;
    }
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      setCopied(true);
    } catch {
      view.copyBlocked();
    }
  };
  const share = () => file && navigator.share({ files: [file] }).catch(() => undefined);

  return createPortal(
    <div
      ref={overlayRef}
      className={cn("fixed inset-0 z-[70] flex items-center justify-center bg-black/70", narrow ? "p-1.5" : "p-3")}
      onClick={onClose}
    >
      <div
        className={cn(
          "flex max-h-full min-w-[300px] flex-col gap-3 rounded-md border border-border2 bg-surface",
          narrow ? "p-1.5" : "p-4",
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="relative flex items-center justify-center">
          <h2 className="font-display text-[15px] tracking-[0.18em] text-text">SHARE YOUR DECK</h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="absolute right-0 text-subtle hover:text-text"
          >
            <X size={18} />
          </button>
        </div>
        <div>
          <div
            className="relative mx-auto overflow-hidden rounded bg-bg"
            style={{ width: stageWidth * scale, height: Math.max(stageHeight * scale, 160) }}
          >
            {!wasBuilt && !imageShown && (
              <div className="absolute left-0 top-0 origin-top-left" style={{ transform: `scale(${scale})` }}>
                <DeckImage view={view} />
              </div>
            )}
            {imageUrl && (
              <img
                src={imageUrl}
                alt="Your deck"
                onLoad={() => setImageShown(true)}
                className={cn("absolute inset-0 h-full w-full object-contain", !imageShown && "opacity-0")}
              />
            )}
            {!failed && (!imageShown || !sweptOnce) && (
              <div className="share-shine pointer-events-none absolute inset-0" />
            )}
          </div>
        </div>
        <div
          className={cn(
            "relative flex flex-wrap items-center justify-end gap-2",
            narrow && "[&>*:not(:first-child)]:flex-1 [&>*:not(:first-child)]:justify-center",
          )}
        >
          <span
            className={cn(
              "pointer-events-none whitespace-nowrap text-center",
              narrow ? (failed ? "basis-full" : "hidden") : "absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2",
            )}
          >
            {failed ? (
              <span className="text-[13px] text-subtle">The image didn't build. Try again</span>
            ) : copied && imageUrl ? (
              !narrow && (
                <span className="font-display text-[13px] tracking-[0.2em] text-green">COPIED TO CLIPBOARD</span>
              )
            ) : (
              !imageUrl &&
              !narrow && (
                <span className="font-display text-[13px] tracking-[0.2em] text-green">
                  BUILDING YOUR IMAGE
                  <span className="loading-dots">
                    <span>.</span>
                    <span>.</span>
                    <span>.</span>
                  </span>
                </span>
              )
            )}
          </span>
          {canShare && (
            <ShareAction disabled={!file} onClick={share} icon={<Share2 size={15} />} label="Share" />
          )}
          <ShareAction
            disabled={false}
            onClick={async () => {
              if (!(await arenaCopy.copy(view.builder.arenaList()))) {
                view.copyBlocked();
              }
            }}
            icon={arenaCopy.copied ? <Check size={15} /> : <img src={ARENA_ICON} alt="" className="h-4 w-auto" />}
            label={arenaCopy.copied ? "Copied" : "Copy for Arena"}
            widestLabel="Copy for Arena"
          />
          {imageUrl ? (
            <a href={imageUrl} download={fileName} className={cn(ACTION_CLASS, chipClass(false))}>
              <Download size={15} />
              Download
            </a>
          ) : (
            <button type="button" disabled className={cn(ACTION_CLASS, chipClass(false), !narrow && "opacity-40")}>
              {narrow && !failed ? (
                <span className="text-green">
                  BUILDING
                  <span className="loading-dots">
                    <span>.</span>
                    <span>.</span>
                    <span>.</span>
                  </span>
                </span>
              ) : (
                <>
                  <Download size={15} />
                  DOWNLOAD
                </>
              )}
            </button>
          )}
          {(canCopy || pretendCopy) && (
            <button
              type="button"
              disabled={!blob}
              onClick={copy}
              className={cn("flex h-9 items-center justify-center gap-2 px-5 disabled:opacity-50", GREEN_CTA)}
            >
              <span className="flex w-4 justify-center">{copied ? <Check size={16} /> : <Copy size={16} />}</span>
              <span className="grid">
                <span className="invisible col-start-1 row-start-1">COPIED</span>
                <span className="col-start-1 row-start-1 text-center">{copied ? "COPIED" : "COPY"}</span>
              </span>
            </button>
          )}
        </div>
      </div>
      <OffscreenDeck view={view} stageRef={stageRef} />
    </div>,
    document.body,
  );
};

export const ShareImageWarmup = ({ view }: { view: BuilderView }) => {
  const stageRef = useRef<HTMLDivElement>(null);
  const [imageKey] = useState(() => shareImageKey(view));
  useEffect(() => {
    const node = stageRef.current;
    if (!node || builtImages.has(imageKey)) {
      return;
    }
    const start = () => void buildShareImage(node, imageKey).catch(() => undefined);
    if (typeof window.requestIdleCallback === "function") {
      const handle = window.requestIdleCallback(start, { timeout: 3000 });
      return () => window.cancelIdleCallback(handle);
    }
    const timer = window.setTimeout(start, 1000);
    return () => window.clearTimeout(timer);
  }, [imageKey]);
  return createPortal(<OffscreenDeck view={view} stageRef={stageRef} />, document.body);
};

const OffscreenDeck = ({ view, stageRef }: { view: BuilderView; stageRef: RefObject<HTMLDivElement> }) => (
  <div aria-hidden className="pointer-events-none fixed left-[-100000px] top-0">
    <div ref={stageRef}>
      <DeckImage view={view} />
    </div>
  </div>
);

const builtImages = new Map<string, Blob>();

const shareImageKey = (view: BuilderView) =>
  JSON.stringify([view.pool.day, view.builder.layout.deck, view.builder.layout.basicsSlot, view.builder.basics, view.builder.sort.deck]);

const buildShareImage = async (node: HTMLElement, imageKey: string) => {
  const fontEmbedCSS = await shareFontCss();
  const blob = await toBlob(node, { pixelRatio: 2, backgroundColor: getComputedStyle(document.body).backgroundColor, fontEmbedCSS });
  if (blob) {
    builtImages.clear();
    builtImages.set(imageKey, blob);
  }
  return blob;
};

const ACTION_CLASS = "flex h-9 items-center gap-2 px-4 text-[13px] tracking-[0.12em] no-underline";

const ShareAction = ({
  disabled,
  onClick,
  icon,
  label,
  widestLabel = label,
}: {
  disabled: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  widestLabel?: string;
}) => (
  <button type="button" disabled={disabled} onClick={onClick} className={cn(ACTION_CLASS, chipClass(false), "disabled:opacity-40")}>
    <span className="flex w-4 justify-center">{icon}</span>
    <span className="grid">
      <span className="invisible col-start-1 row-start-1">{widestLabel.toUpperCase()}</span>
      <span className="col-start-1 row-start-1 text-center">{label.toUpperCase()}</span>
    </span>
  </button>
);

const DeckImage = ({ view }: { view: BuilderView }) => {
  const rows = deckGroupRows(view).map(sameOriginImages);
  const colors = view.builder.submission().colors;
  return (
    <div className="flex w-max min-w-[640px] flex-col gap-4 bg-bg px-6 pb-3 pt-6 text-text">
      <div className="flex items-center gap-4">
        <SetGlyph code={view.pool.setCode} size={22} />
        <span className="font-display text-[18px] tracking-[0.12em] text-subtle">
          {view.setName.toUpperCase()} POOL <span className="text-green">#{view.pool.poolNumber}</span>
        </span>
        <span className="ml-auto flex items-center gap-3">
          {colors && <Pips colors={colors} size={15} />}
          <span className="font-display text-[18px] tracking-[0.12em] text-subtle">{formatDay(view.pool.day)}</span>
        </span>
      </div>
      {rows.map((groups, index) => (
        <ColumnRow key={index} groups={groups} setCode={view.pool.setCode} width={IMAGE_CARD_WIDTH} actions={NO_ACTIONS} />
      ))}
      <span className="-mr-3 self-end font-display text-[15px] leading-none tracking-[0.12em] text-subtle">
        limitedlevelups.com/daily-sealed
      </span>
    </div>
  );
};

const NO_ACTIONS = { onPick: () => undefined, onPreview: () => undefined };

const sameOriginImages = (groups: CardGroup[]): CardGroup[] =>
  groups.map((group) => ({
    ...group,
    entries: group.entries.map((entry) => ({ ...entry, card: { ...entry.card, image: sameOriginImage(entry.card.image) } })),
  }));

const sameOriginImage = (url: string) =>
  url.startsWith(CARD_IMAGE_HOST) ? `/api/card-art/${url.slice(CARD_IMAGE_HOST.length)}` : url;

const canShareFiles = () => {
  if (typeof navigator.canShare !== "function") {
    return false;
  }
  try {
    return navigator.canShare({ files: [new File([], "deck.png", { type: "image/png" })] });
  } catch {
    return false;
  }
};

let shareFontCssOnce: Promise<string> | null = null;

const shareFontCss = () => {
  shareFontCssOnce ??= buildShareFontCss().catch((error) => {
    shareFontCssOnce = null;
    throw error;
  });
  return shareFontCssOnce;
};

const buildShareFontCss = async () => {
  const hankenCss = await (await fetch(HANKEN_GROTESK_CSS)).text();
  const hankenLatin = [...hankenCss.matchAll(/\/\* latin \*\/\s*(@font-face\s*\{[^}]*\})/g)].map((match) => match[1]);
  const faces = [
    `@font-face { font-family: "Bebas Neue"; font-weight: 400; src: url("/fonts/bebas-neue-latin.woff2") format("woff2"); ascent-override: 85%; descent-override: 15%; line-gap-override: 0%; }`,
    `@font-face { font-family: "Mana"; font-weight: normal; src: url("${MANA_FONT}") format("woff"); }`,
    ...hankenLatin,
  ];
  return (await Promise.all(faces.map(inlineFontUrls))).join("\n");
};

const inlineFontUrls = async (face: string) => {
  let inlined = face;
  for (const [, url] of face.matchAll(/url\(["']?([^"')]+)["']?\)/g)) {
    inlined = inlined.replace(url, await dataUrlOf(url));
  }
  return inlined;
};

const dataUrlOf = async (url: string) => {
  const blob = await (await fetch(url)).blob();
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
};

const deferredBlob = () => {
  let resolve: (blob: Blob) => void = () => undefined;
  let reject: (error: Error) => void = () => undefined;
  const promise = new Promise<Blob>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  promise.catch(() => undefined);
  return { promise, resolve, reject };
};
