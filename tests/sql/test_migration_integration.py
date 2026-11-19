"""Live test against the dev Managed Instance. Skipped unless DATAENGINE_TEST_SQL=1.

Setup (see docs/core_schema.md):
  DATAENGINE_TEST_SQL=1
  DATAENGINE_SQL_SERVER=<dev MI host>
  DATAENGINE_SQL_DATABASE=Listmanagement_core_test   (an empty database)
  password for dataengine_pipeline in Credential Manager (service "dataengine")

The test never drops anything. On an empty database the first run applies
V001; on any database the second run must apply nothing and change nothing.
"""
from __future__ import annotations

import os

import pytest

from sql.runner import connection, migrate

from .test_migration_static import EXPECTED_TABLES

pytestmark = pytest.mark.skipif(os.environ.get("DATAENGINE_TEST_SQL") != "1",
                                reason="set DATAENGINE_TEST_SQL=1 to run against the dev Managed Instance")

SNAPSHOT_SQL = """
SELECT o.name, o.type, o.modify_date
FROM sys.objects o
WHERE o.is_ms_shipped = 0
ORDER BY o.name;
"""


def snapshot(conn):
    return [tuple(r) for r in conn.cursor().execute(SNAPSHOT_SQL).fetchall()]


@pytest.fixture(scope="module")
def conn():
    assert connection.target_database().lower() != "listmanagement_core", \
        "point DATAENGINE_SQL_DATABASE at the test database, not the real core"
    c = connection.connect()
    yield c
    c.close()


def test_migration_runs_twice_with_no_changes(conn):
    was_empty = not migrate.applied_checksums(conn)
    first = migrate.migrate(conn)
    if was_empty:
        assert "V001__core_schema.sql" in first

    tables = {r[0] for r in conn.cursor().execute(
        "SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID('dbo');").fetchall()}
    assert EXPECTED_TABLES | {"SchemaVersion"} <= tables

    level = conn.cursor().execute(
        "SELECT compatibility_level FROM sys.databases WHERE database_id = DB_ID();").fetchone()[0]
    assert level == 160

    before = snapshot(conn)
    versions_before = migrate.applied_checksums(conn)
    assert migrate.migrate(conn) == []
    assert snapshot(conn) == before
    assert migrate.applied_checksums(conn) == versions_before


def test_v001_is_idempotent_when_run_directly(conn):
    """Running the script itself again (bypassing the runner) is also a no-op."""
    before = snapshot(conn)
    cur = conn.cursor()
    for batch in migrate.split_batches(migrate.discover()[0].text):
        cur.execute(batch)
    conn.commit()
    assert snapshot(conn) == before
