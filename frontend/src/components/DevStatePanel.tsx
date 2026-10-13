import { useState, type ReactNode } from "react";
import { devToolsEnabled } from "../lib/dev-preset-store";

export type DevStateOption<T extends string> = { value: T; group: string; label: string };

export function DevStatePanel<T extends string>({
  title,
  options,
  value,
  onChange,
  liveValue,
  children,
}: {
  title: string;
  options: DevStateOption<T>[];
  value: T;
  onChange: (value: T) => void;
  liveValue: T;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  if (!devToolsEnabled) {
    return null;
  }
  const selected = options.find((option) => option.value === value);
  const selectedLabel = selected && selected.group !== selected.label ? `${selected.group} - ${selected.label}` : value;

  return (
    <div className="fixed bottom-3 right-3 z-[100] flex flex-col items-end gap-2 font-display">
      {open && (
        <div className="flex flex-col gap-0.5 rounded-md border border-green bg-black p-1.5 shadow-lg">
          <div className="px-1 pb-0.5 text-[11px] tracking-[0.14em] text-green">{title}</div>
          {[...new Set(options.map((option) => option.group))].map((group) => (
            <div key={group} className="flex flex-col gap-0.5">
              {group !== "Live" && (
                <div className="px-1 pt-1 text-[10px] tracking-[0.18em] text-green/60">{group.toUpperCase()}</div>
              )}
              {options
                .filter((option) => option.group === group)
                .map((option) => (
                  <DevStateButton
                    key={option.value}
                    label={option.label}
                    active={option.value === value}
                    onClick={() => onChange(option.value)}
                  />
                ))}
            </div>
          ))}
          {children}
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((isOpen) => !isOpen)}
        className="mb-2 mr-1 rounded-full border border-green bg-black px-4 py-2.5 text-[13px] tracking-wide text-green shadow-lg"
      >
        DEV {value === liveValue ? "" : `- ${selectedLabel}`}
      </button>
    </div>
  );
}

export function DevStateSection<T extends string>({
  title,
  options,
  value,
  onChange,
}: {
  title: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <>
      <div className="mt-1 px-1 pb-0.5 text-[11px] tracking-[0.14em] text-green border-t border-green/30 pt-1.5">
        {title}
      </div>
      {options.map((option) => (
        <DevStateButton
          key={option.value}
          label={option.label}
          active={option.value === value}
          onClick={() => onChange(option.value)}
        />
      ))}
    </>
  );
}

function DevStateButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded px-3 py-1.5 text-left text-[14px] tracking-wide transition-colors ${
        active ? "bg-green text-black" : "text-green hover:bg-green/20"
      }`}
    >
      {label}
    </button>
  );
}
