# brain_db handoff package

Design specification and implementation scaffolding for the ERP Brain database (`brain_db`).
Start with `docs/01_architecture_traceability_conventions.md`.

    docs/    4-part specification (architecture and traceability; every table; lifecycle, security, performance, tests; migrations, backlog, open decisions, handoff)
    ddl/     PostgreSQL DDL per migration (0001-0008; 0007 = tenant registry + row-level security, 0008 = least privilege (D-51); both with a .down.sql)
             + brain_db_mvp.sql (concatenation) + optional_future_rag.sql
             + bootstrap_roles.sql (runtime roles, once per cluster, CREATEROLE admin) + handover_ownership.sql (D-50)
    python/  SQLModel models, Pydantic JSONB/feature contracts, Alembic helper, brain/db/session.py (engines, unit of work; D-47)
    alembic/ environment and eight revisions that execute the DDL files
    verification/ PG16 check scripts: decisions, proposal lifecycle, roles (D-45, D-51), tenancy and RLS (D-46, D-47); no superuser (bbsetup.py)
    tests/   pytest integration harness: session.py tests and the four verification suites (tests/integration/README.md)
    erd/     Mermaid sources for every diagram
    tools/   schema definition and generator (reference)

Verified only in a local PostgreSQL 16 sandbox (21 Oct 2026), not yet in CI. Quick start for a scratch database:

    psql -U <role admin with CREATEROLE> -d postgres -f ddl/bootstrap_roles.sql      # once per cluster (D-50)
    export BRAIN_DB_MIGRATION_URL=postgresql+psycopg://owner:***@localhost:5432/brain_db   # database owner, no role attributes
    alembic upgrade head && alembic check
    BB_ADMIN_DSN=... BB_OWNER_DSN=... BB_TEST_DB=... pytest      # integration tests, see tests/integration/README.md
