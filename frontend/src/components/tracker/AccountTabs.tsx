import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { cn } from "../../lib/utils";
import { Tooltip } from "../Tooltip";
import { fetchMyAccounts, type TrackerAccount } from "../../data/trackerApi";

/** player_accounts names carry an Arena discriminator ("Noya — CA4E"); the tab wants the handle */
function shortAccountName(name: string): string {
  return name.split(/[—-]/)[0].trim() || name;
}

/** One account is always selected, so the tracker opens on the busiest one */
export function useTrackerAccounts(enabled: boolean) {
  const { data } = useQuery({ queryKey: ["tracker-accounts"], queryFn: fetchMyAccounts, enabled });
  const [chosen, setChosen] = useState<number | null>(null);
  const accounts = data ?? [];
  return {
    accounts,
    accountId: chosen ?? accounts[0]?.accountId ?? null,
    setAccountId: setChosen,
  };
}

export function AccountTabs({
  accounts, active, onChange, className,
}: {
  accounts: TrackerAccount[];
  active: number | null;
  onChange: (id: number) => void;
  className?: string;
}) {
  if (accounts.length < 2) {
    return null;
  }

  return (
    <span className={cn("flex gap-[1px] bg-border border border-border", className)}>
      {accounts.map((a) => (
        <Tooltip key={a.accountId} label={`${a.events} drafts`}>
          <button
            onClick={() => onChange(a.accountId)}
            className={cn(
              "font-display text-[13px] tracking-[0.12em] px-3 py-1",
              active === a.accountId ? "bg-green text-bg" : "bg-surface text-muted hover:text-text",
            )}
          >
            {shortAccountName(a.accountName)}
          </button>
        </Tooltip>
      ))}
    </span>
  );
}
