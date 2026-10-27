# docs

Project documents for the AI Brain. They were written in the team workspace before the Brain code entered this repository, and are copied here unchanged.

## Precedence

When two documents disagree, the earlier one in this list wins:

1. `BLUEPRINT_FINAL.md`: final MVP blueprint (21 Oct 2026)
2. `decisions/DECISIONS_2026-10-21_ERD.md` (D-27 to D-51), which extends the blueprint's decision register
3. `decisions/DECISIONS_v1.md` (D-01 to D-22; rows marked superseded there no longer apply)
4. `apps/brain/brain_db/docs/MVP_DECISIONS_AND_CONTRACTS.md`
5. the Brain contracts kit (not in this repository yet, see below)
6. `apps/brain/brain_db/docs/`
7. `architecture/`

## Contents

| File | What it is |
|---|---|
| `BLUEPRINT_FINAL.md` | Final MVP blueprint and decision register |
| `TEAM_TASKS.md` | AI team task pack (BB-01 to BB-25) with acceptance criteria |
| `decisions/DECISIONS_v1.md` | Decision record v1 (D-01 to D-22) |
| `decisions/DECISIONS_2026-10-21_ERD.md` | ERD and database decisions (D-27 to D-51) |
| `decisions/ERD_DB_APPROVAL_QUESTIONS.md` | Answered questions (Q-01 to Q-14) and the open ones (N-xx) |
| `decisions/CHANGES_2026-10-21.md`, `decisions/IMPACT_2026-10-21_*.md` | What each decision changed, with the checks run at the time |
| `decisions/CROSS_DOCUMENT_CONSISTENCY_AUDIT.md` | 17 Oct audit; source of the F-xx conflict references used in `DECISIONS_v1.md` |
| `architecture/ERP-Brain-Architecture-Blueprint.md` | Architecture blueprint v1.1 (17 Oct). Background only: where it mentions Redis Streams, ERP events or an event consumer, `BLUEPRINT_FINAL.md` replaces it |
| `CONTRACT-QUESTIONS.md` | Frontend contract questions (already in the repository; not part of the Brain set) |

## Paths in these documents

The documents use the workspace layout. In this repository:

| Path in the documents | Path here |
|---|---|
| `brain_db/` | `apps/brain/brain_db/` |
| `contracts/internal/brain_ports.py` | `apps/brain/brain/ports.py` (verbatim copy; CI checks its SHA-256, decision D-6b) |
| `contracts/README.md`, `contracts/schemas/`, `contracts/openapi/`, `contracts/fixtures/`, `contracts/internal/BRAIN_CONTRACTS.md`, `contracts/internal/brain.env.example` | Not in this repository yet. The Brain contracts kit is still marked proposed and needs its own contracts pull request with `/contracts/` owner sign-off (D-6b). The `contracts/` folder here is the ERP frontend kit: its `contracts/README.md` is the ERP frontend contracts README, not the Brain kit README these documents cite |
| `Answers/`, `docs/status/`, `_archive/` | Not copied (personal notes, a dated status snapshot and duplicates) |
| `docs/architecture/AI_BRAIN_TEAM_EXECUTION_BLUEPRINT.md`, `docs/architecture/دليل الـTeam Lead لمشروع ERP Brain.md` | Not copied; they stay in the team workspace. `decisions/CROSS_DOCUMENT_CONSISTENCY_AUDIT.md` cites them |

## Labels D-6a, D-6b and D-6c

These labels come from commit `a06db63` ("Stage 6: brain_db under version control with a brain-ci gate on PostgreSQL 16") in `stage6-brain-ci.bundle`; that commit is not part of this repository's history. They are not entries in the D-01 to D-51 decision registers (D-06 there is a different decision). The available evidence records only which work each label is attached to; the original decision text could not be found.

| Label | Attached to | Source |
|---|---|---|
| D-6a, D-6b | `apps/brain/brain_db/` was copied unchanged except two path lines: `tests/harness.py` imports `brain.ports`, and `pytest.ini` adds `..` to `pythonpath` | Commit message of `a06db63` |
| D-6b | `apps/brain/brain/ports.py` is a verbatim copy of `contracts/internal/brain_ports.py` with SHA-256 `695bb0c3d2ee93fa4f214ef7e6f2f0e675573e70485db1b7bfc26cac532a1dcf`; `brain-ci` fails if the file's hash differs | Commit message of `a06db63`; `.github/workflows/ci.yml` |
| D-6b | The Brain contracts kit needs its own contracts pull request with `/contracts/` owner sign-off | The path table above (no other source found) |
| D-6c | `.github/workflows/ci.yml` changes the `brain-ci` job only. The database superuser is used in one setup step only (a server version check, then `CREATE ROLE bb_admin`, `CREATE ROLE brain_migrator` and `CREATE DATABASE brain_it`); everything after it runs as `bb_admin` or `brain_migrator`. `bb_admin` and `CREATEROLE` are CI-only: `brain-ci` fails if either appears in `infrastructure/` or `.env.example`, and 13 escalation attempts as `bb_admin` must be refused | Commit message of `a06db63`; `.github/workflows/ci.yml` |

## What these documents do not prove

They are plans and decision records. Only `apps/brain/brain_db/` is implemented. These items stay open until their own acceptance criteria pass:

- BB-24 (application-level tenant isolation) is open: no Brain application code exists yet.
- Stage 5 is accepted with limited scope only.
- The open N-xx questions in `decisions/ERD_DB_APPROVAL_QUESTIONS.md`, and the unsigned Canonical part of D-49.

## Readiness-audit blockers B1, B2, B6 and B7

These database blockers (listed in `decisions/IMPACT_2026-10-21_N01_N02_N05.md`) had one closure condition: a green GitHub Actions run of `brain-ci`. That condition is met by run 39822104031, triggered by the push to `main` of merge commit `4a2e85831b1efe03dec3d856d55853d2cedefc7c`. GitHub reports the workflow run and the `brain-ci` job as successful, with every `brain-ci` step successful. The job log could not be downloaded (it needs admin rights on the repository), so its contents, such as the pytest summary line, have not been inspected; the closure rests on GitHub's reported job and step results. Each step below fails unless its check passes.

| Blocker | As recorded | `brain-ci` step that checks it |
|---|---|---|
| B1 | `brain_app` grants; addressed by D-51 (migration 0008) | "Integration and isolation tests (41, none skipped)": `role_security_checks.py` (D-45, D-51) and `test_api_login_cannot_write_pipeline_tables_or_rule_sets` |
| B2 | Migrations needed a superuser; addressed by D-50 | "Runtime roles as bb_admin, then alembic upgrade head and alembic check as brain_migrator": the migration owner has no SUPERUSER, BYPASSRLS, CREATEROLE or CREATEDB and runs `alembic upgrade head` |
| B6 | `alembic check` reported differences | The same step runs `alembic check` |
| B7 | `brain_worker` grants; addressed by D-51 (migration 0008) | "Integration and isolation tests (41, none skipped)": `role_security_checks.py` (D-45, D-51) |

The dated records in `decisions/` (`IMPACT_2026-10-21_N01_N02_N05.md`, `IMPACT_2026-10-21_N09.md`) still list these blockers as open: they record the state on 21 Oct 2026 and are kept unchanged.
