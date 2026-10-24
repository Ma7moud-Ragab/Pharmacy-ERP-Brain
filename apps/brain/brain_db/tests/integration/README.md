# brain_db integration tests

PostgreSQL 16, pytest, psycopg 3, SQLAlchemy 2, SQLModel, Alembic. No test connection is a superuser (D-50): the
harness refuses to start if `BB_ADMIN_DSN` or `BB_OWNER_DSN` is SUPERUSER or BYPASSRLS, and every check runs through a
test login granted exactly one runtime role.

## One-time cluster setup (infrastructure, not part of the tests)

Run once per test cluster by whoever administers it (in CI: the PostgreSQL service's bootstrap user, in the job's
service-setup step):

```sql
CREATE ROLE bb_admin LOGIN CREATEROLE;           -- role administrator: CREATEROLE only, nothing else
CREATE ROLE brain_migrator LOGIN;                -- migration owner: no role attributes
CREATE DATABASE brain_it OWNER brain_migrator;   -- test database; its contents are dropped and rebuilt by the tests
```

`bb_admin` must be the role that creates the runtime roles (`ddl/bootstrap_roles.sql`; the harness runs it), so it holds
ADMIN OPTION on them and can grant them to test logins. If the runtime roles already exist from another creator, the
cluster administrator grants them once: `GRANT brain_app, brain_worker, brain_retention, brain_readonly,
brain_provisioner TO bb_admin WITH ADMIN OPTION;`

## Run

```sh
cd brain_db
export BB_ADMIN_DSN="host=localhost port=5432 user=bb_admin password=..."
export BB_OWNER_DSN="host=localhost port=5432 user=brain_migrator password=..."
export BB_TEST_DB=brain_it
pytest
```

Missing variables fail the run; integration tests are never skipped.

## What runs

* `test_session.py`: `brain/db/session.py` against real logins: the startup login check, the unit of work's tenant
  context, cross-tenant reads and writes, rollback, the worker's registry scan, and audited rule-set changes carrying
  the RunContext's actor and trace id. Pooled-connection reset, the checkout guard and thread interleaving are BB-24
  group 7, in `tests/isolation/` (README there).
* `test_verification_suites.py`: the four scripts in `verification/` (20, 69, 49 and 115 checks), each on a freshly
  migrated database, through the same superuser-free setup (`verification/bbsetup.py`).

Each test module starts from `fresh_database()` (fixtures in `tests/conftest.py`, helpers in `tests/harness.py`): the owner drops every Brain object, `bootstrap_roles.sql` runs as the
administrator, then `alembic upgrade head` and `alembic check` run as the owner. Tenants A and B are provisioned
through the `brain_provisioner` login and their rows written by the `brain_worker` and `brain_app` logins.
