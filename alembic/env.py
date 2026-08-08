from alembic import context
from sqlalchemy import engine_from_config, pool

from bot.config import settings
from bot.models import Base

# Skip alembic.ini's [logger_*] config — disable_existing_loggers=True there silently kills bot/discord loggers
config = context.config
# Escape % so configparser doesn't try to interpolate (Supabase pooler passwords contain percent-encoded chars like %2B)
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = Base.metadata


UNMODELED_SCHEMAS = frozenset({"auth"})


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """Hide constraints pointing into schemas the models cannot describe.

    Supabase owns `auth`, so a local database mirrored from production carries a foreign key from
    p0p1_entries into auth.users that no migration created and no model can declare. Without this,
    `alembic check` reports permanent drift against any prod-derived database and a real one gets lost
    among the noise. A database built from the migrations alone, which is what CI checks, never has it.
    """
    if type_ == "foreign_key_constraint":
        referred = getattr(obj, "referred_table", None)
        if referred is not None and referred.schema in UNMODELED_SCHEMAS:
            return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
