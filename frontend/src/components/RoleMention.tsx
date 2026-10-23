type DiscordRole = "Organizer" | "Set Champion" | "Pod Champion";

export function RoleMention({ role }: { role: DiscordRole }) {
  const roleColors: Record<DiscordRole, string> = {
    Organizer: "#f38300",
    "Set Champion": "#82cbff",
    "Pod Champion": "#e7a855",
  };
  const color = roleColors[role];
  return (
    <span
      className="whitespace-nowrap rounded-[3px] px-0.5 font-medium"
      style={{ color, backgroundColor: `${color}1a` }}
    >
      @{role}
    </span>
  );
}
