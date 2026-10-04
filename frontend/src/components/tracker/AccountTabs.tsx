import { useState } from "react";

import { cn } from "../../lib/utils";
import { useAuth } from "../../auth/useAuth";
import { trackerAccountsFor, type TrackerAccount } from "../../data/trackerUsers";

/** One account is always selected, so the tracker opens on the first listed one */
export function useTrackerAccounts(enabled: boolean) {
  const { user } = useAuth();
  const [chosen, setChosen] = useState<number | null>(null);
  const accounts = enabled ? trackerAccountsFor(user?.discordId) : [];
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
        <button
          key={a.accountId}
          onClick={() => onChange(a.accountId)}
          className={cn(
            "font-display text-[13px] tracking-[0.12em] px-3 py-1",
            active === a.accountId ? "bg-green text-bg" : "bg-surface text-muted hover:text-text",
          )}
        >
          {a.accountName}
        </button>
      ))}
    </span>
  );
}
