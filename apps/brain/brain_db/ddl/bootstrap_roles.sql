-- bootstrap_roles.sql (B2, D-50): create the Brain runtime roles. Run ONCE per cluster, before `alembic upgrade`,
-- as a role administrator with CREATEROLE (not the migration owner). Safe to re-run: existing roles are skipped.
-- Migrations never create or alter roles when the migrator is not a superuser; they only verify these.
DO $do$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_app') THEN CREATE ROLE brain_app NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_worker') THEN CREATE ROLE brain_worker NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_retention') THEN CREATE ROLE brain_retention NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_readonly') THEN CREATE ROLE brain_readonly NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'brain_provisioner') THEN CREATE ROLE brain_provisioner NOLOGIN; END IF;
END $do$;
-- Login users are created per environment and granted ONE of these roles (never brain_app and brain_worker together).
