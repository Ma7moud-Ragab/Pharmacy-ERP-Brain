"""Alembic environment for brain_db (SQLModel metadata, five schemas, sync driver).

Connection string comes from BRAIN_DB_MIGRATION_URL (migration-owner role, NOT the application role), e.g.
postgresql+psycopg://brain_migrator:***@db:5432/brain_db

The migration owner needs no role attributes (no SUPERUSER, no CREATEROLE; D-50). The runtime roles are created once
per cluster by a role administrator with ddl/bootstrap_roles.sql; a non-superuser run stops before the first revision
if they are missing or carry a forbidden attribute. A database built earlier by a superuser migrator needs
ddl/handover_ownership.sql once (DBA) before it can be upgraded by the non-superuser owner.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlmodel import SQLModel

import brain.db.models  # noqa: F401  (registers all tables on SQLModel.metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata
SCHEMAS = {"ingest", "feat", "intel", "agent", "audit"}
RUNTIME_ROLES = ("brain_app", "brain_worker", "brain_retention", "brain_readonly", "brain_provisioner")


def include_object(obj, name, type_, reflected, compare_to):
    # Only manage objects in the five brain schemas; ignore alembic_version in public.
    if type_ == "table":
        return getattr(obj, "schema", None) in SCHEMAS
    return True


def _url() -> str:
    url = os.environ.get("BRAIN_DB_MIGRATION_URL")
    if not url:
        raise RuntimeError("BRAIN_DB_MIGRATION_URL is not set")
    return url


def _preflight(connection) -> None:
    """D-50 (B2): check the bootstrapped runtime roles before any revision runs, so a missing bootstrap fails with
    nothing committed (revisions run one transaction each). A superuser migrator is not checked: 0005/0007 create the
    roles themselves in that case."""
    try:
        if connection.execute(text("SELECT current_setting('is_superuser')")).scalar() == "on":
            return
        found = dict(connection.execute(text(
            "SELECT rolname, (rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls OR rolcanlogin) "
            "FROM pg_roles WHERE rolname = ANY(:names)"), {"names": list(RUNTIME_ROLES)}).all())
        missing = [r for r in RUNTIME_ROLES if r not in found]
        if missing:
            raise RuntimeError(f"runtime roles missing: {', '.join(missing)}. "
                               "Run ddl/bootstrap_roles.sql once per cluster as a role administrator (CREATEROLE).")
        forbidden = sorted(r for r, bad in found.items() if bad)
        if forbidden:
            raise RuntimeError(f"runtime roles must be NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION "
                               f"NOBYPASSRLS: {', '.join(forbidden)}")
    finally:
        connection.rollback()  # close the read-only transaction this check opened, so Alembic commits its own


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), target_metadata=target_metadata, literal_binds=True, include_schemas=True,
        include_object=include_object, version_table_schema="public", compare_type=True,
        compare_server_default=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = _url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        _preflight(connection)
        context.configure(
            connection=connection, target_metadata=target_metadata, include_schemas=True,
            include_object=include_object, version_table_schema="public", compare_type=True,
            compare_server_default=False, transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
