from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DRAFTMANCER_HOST = "draftmancer.com"

PRODUCTION_GUILD_ID = 775371722065051658

OWNER_DISCORD_ID = 237762740532412416


class Settings(BaseSettings):
    """Process-wide configuration loaded from env (or .env in repo root).

    Discord fields are optional so non-bot entry points (alembic CLI, the
    seed script, tests) can construct Settings without them.

    The active set is derived from today's date in ``bot/sets.py``, not here —
    rotation needs no config change.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    discord_bot_token: SecretStr | None = None
    discord_guild_id: int | None = None
    discord_admin_role_id: int | None = None
    discord_botlog_channel_id: int | None = None
    feedback_channel_id: int = 1504825374188507156
    public_site_url: str = "https://limitedlevelups.com"
    auto_refresh_enabled: bool = True
    tracker_discord_ids: str = str(OWNER_DISCORD_ID)
    pod_thread_watch_id: int | None = OWNER_DISCORD_ID
    supabase_url: str = ""
    supabase_anon_key: str = ""
    tracker_http_port: int | None = None

    @property
    def tracker_discord_ids_set(self) -> frozenset[str]:
        return frozenset(part.strip() for part in self.tracker_discord_ids.split(",") if part.strip())

    @property
    def leaderboard_url(self) -> str:
        return f"{self.public_site_url.rstrip('/')}/leaderboard"

    @property
    def player_base_url(self) -> str:
        return f"{self.public_site_url.rstrip('/')}/player"

    format_schedule_enabled: bool = True

    pod_draft_channel_id: int = 1028072146645295125
    discord_botlog_channel_name: str = "bot-spam"
    pod_draft_chat_channel_name: str = "pod-draft-chat"
    pod_draft_trophy_hype_channel_name: str = "trophy-hype"
    pod_draft_target_players: int = 8
    pod_draft_voice_channel_name: str = "Pod General"
    pod_schedule_enabled: bool = True
    pod_draft_session_prefix: str = "LLU"
    pod_draft_max_players: int = 8
    pod_draft_min_ready_players: int = 6
    pod_table_open_threshold: int = 4
    pod_round_robin_size: int = 4
    pod_draft_pick_timer: int = 60
    pod_draft_picks_per_pack: int = 1
    pod_draft_fallback_tz: str = "America/New_York"
    pod_draft_skip_reminder_wait: bool = False
    pod_draft_end_watchdog_minutes: int = 90
    pod_signal_fire_threshold: int = 6
    pod_queue_inactivity_minutes: int = 180
    pod_idle_offer_minutes: int = 30
    pod_self_destruct_grace_minutes: int = 5
    pod_underfill_check_hours: str = "3,2,1"
    pod_underfill_ping_hours: str = "1"
    pod_underfill_ping_close_gap: int = 2

    @property
    def pod_underfill_check_hours_tuple(self) -> tuple[int, ...]:
        return _int_csv(self.pod_underfill_check_hours)

    @property
    def pod_underfill_ping_hours_set(self) -> frozenset[int]:
        return frozenset(_int_csv(self.pod_underfill_ping_hours))

    draftmancer_ws_url: str = f"wss://{DRAFTMANCER_HOST}"
    draftmancer_web_url: str = f"https://{DRAFTMANCER_HOST}"

    youtube_api_key: SecretStr | None = None
    youtube_channel_handle: str = "limitedlevel-ups"
    libsyn_feed_url: str = "https://feeds.libsyn.com/limitedlevelups/rss"
    media_sync_enabled: bool = True
    profile_sync_enabled: bool = True


    @property
    def is_production(self) -> bool:
        """Whether this process is the community bot. The test bot runs the same code against its own guild,
        so behavior that belongs to one of them keys off the guild it is actually in."""
        return self.discord_guild_id == PRODUCTION_GUILD_ID


def _int_csv(raw: str) -> tuple[int, ...]:
    return tuple(int(part) for part in raw.split(",") if part.strip())


settings = Settings()
