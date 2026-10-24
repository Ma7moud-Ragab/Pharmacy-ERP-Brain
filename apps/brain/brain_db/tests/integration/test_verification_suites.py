"""The four database suites in brain_db/verification as pytest cases (BB-05 step 5). Hand-written.

Each suite runs as its own process on a freshly migrated database, with the same superuser-free setup as the rest of
the harness (BB_ADMIN_DSN creates its logins, BB_OWNER_DSN seeds in a tenant context). A case passes only if every
check of the suite passed; a failure lists the failing checks.
"""
import os
import re
import subprocess
import sys

import pytest

from harness import ROOT, env, fresh_database

SUITES = {"decision_checks_2026-10-21.py": 20, "proposal_transition_checks.py": 69, "role_security_checks.py": 49,
          "tenancy_rls_checks.py": 115}


@pytest.mark.parametrize("suite, expected", SUITES.items(), ids=list(SUITES))
def test_suite(suite, expected):
    fresh_database()
    r = subprocess.run([sys.executable, str(ROOT / "verification" / suite), env("BB_TEST_DB")], cwd=ROOT / "verification",
                       env=dict(os.environ, PYTHONPATH=str(ROOT / "verification")), capture_output=True, text=True, timeout=600)
    failed = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
    m = re.search(r"^(\d+)/(\d+) passed$", r.stdout, re.M)
    assert r.returncode == 0 and m and int(m.group(1)) == int(m.group(2)) == expected, \
        f"{suite}: {m.group(0) if m else 'no summary'}\n" + "\n".join(failed[:20]) + f"\n{r.stderr[-2000:]}"
