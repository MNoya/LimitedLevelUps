"""Fail if a public_* view is not readable by both site roles.

    DATABASE_URL=postgresql://... python -m bot.scripts.check_public_grants

A logged-out visitor reads through PostgREST as ``anon`` and a logged-in one as ``authenticated``,
so a view granted to only one of them half-works: the site is fine until someone signs in, and the
failure never reaches a test because the model-built test schema has no public_* objects at all.
Dropping a view drops its grants, so recreating one silently reintroduces this.

Runs in CI after ``alembic upgrade head``, which is the only place the real views and both roles
exist together.
"""
from __future__ import annotations

import logging
import sys

from sqlalchemy import text

from bot.database import SessionLocal


logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("check_public_grants")

SITE_ROLES = ("anon", "authenticated")


def missing_grants(session) -> list[tuple[str, str]]:
    rows = session.execute(text("""
        SELECT c.relname,
               has_table_privilege('anon', c.oid, 'SELECT') AS anon,
               has_table_privilege('authenticated', c.oid, 'SELECT') AS authenticated
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('v', 'm') AND c.relname LIKE 'public\\_%'
        ORDER BY c.relname
    """)).all()
    gaps = []
    for row in rows:
        for role in SITE_ROLES:
            if not getattr(row, role):
                gaps.append((row.relname, role))
    log.info(f"checked {len(rows)} public_* objects")
    return gaps


def main() -> None:
    with SessionLocal() as session:
        for role in SITE_ROLES:
            exists = session.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}
            ).scalar()
            if not exists:
                log.error(f"role {role} does not exist; migrations should have created it")
                sys.exit(1)
        gaps = missing_grants(session)

    if gaps:
        for view, role in gaps:
            log.error(f"{view} is not readable by {role}")
        log.error("grant both site roles when a public_* view is created or recreated")
        sys.exit(1)
    log.info("all public_* objects readable by anon and authenticated")


if __name__ == "__main__":
    main()
