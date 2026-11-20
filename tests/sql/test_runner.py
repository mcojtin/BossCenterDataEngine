"""Unit tests for the migration runner and preflight, using a fake connection."""
from __future__ import annotations

import pytest

from sql.runner import connection, migrate, preflight


class FakeCursor:
    def __init__(self, db):
        self.db = db
        self._rows = []

    def execute(self, sql, *params):
        self.db.executed.append(sql)
        s = sql.strip()
        if s == preflight.SQL_CURRENT_DB:
            self._rows = [(self.db.name, self.db.compat)]
        elif s == preflight.SQL_SET_COMPAT:
            assert self.db.autocommit, "ALTER DATABASE must run outside a transaction"
            self.db.compat = 160
        elif s == preflight.SQL_IN_SIZE_MB:
            self._rows = [(self.db.in_mb,)]
        elif s == preflight.SQL_INSTANCE_STORAGE_MB:
            self._rows = [self.db.storage] if self.db.storage else []
        elif "OBJECT_ID(N'dbo.SchemaVersion'" in s and s.startswith("SELECT"):
            self._rows = [(1 if self.db.has_version_table else None,)]
        elif "CREATE TABLE dbo.SchemaVersion" in s:
            self.db.has_version_table = True
        elif s.startswith("SELECT ScriptName"):
            self._rows = list(self.db.committed.items())
        elif s.startswith("INSERT INTO dbo.SchemaVersion"):
            self.db.pending[params[0]] = params[1]
        elif self.db.fail_on and self.db.fail_on in s:
            raise RuntimeError("boom")
        else:
            self.db.ddl.append(s)
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, compat=160, in_mb=100.0, storage=(1000.0, 500.0), name="Listmanagement_core"):
        self.name, self.compat, self.in_mb, self.storage = name, compat, in_mb, storage
        self.autocommit = False
        self.has_version_table = False
        self.committed: dict[str, str] = {}
        self.pending: dict[str, str] = {}
        self.executed: list[str] = []
        self.ddl: list[str] = []
        self.fail_on = None

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed.update(self.pending)
        self.pending.clear()

    def rollback(self):
        self.pending.clear()


@pytest.fixture
def mig_dir(tmp_path):
    (tmp_path / "V001__one.sql").write_text("CREATE TABLE dbo.A (x int);\nGO\nCREATE TABLE dbo.B (x int);\n")
    (tmp_path / "V002__two.sql").write_text("CREATE TABLE dbo.C (x int);\n")
    (tmp_path / "README.md").write_text("ignored")
    return tmp_path


# --- split_batches / discover ------------------------------------------------

def test_split_batches_on_go_lines_only():
    sql = "SELECT 1;\nGO\n-- only a comment\nGO\nSELECT 'GO';\n  go  \nSELECT 2;"
    assert migrate.split_batches(sql) == ["SELECT 1;", "SELECT 'GO';", "SELECT 2;"]


def test_discover_orders_by_version(tmp_path):
    (tmp_path / "V010__b.sql").write_text("x")
    (tmp_path / "V002__a.sql").write_text("x")
    assert [s.name for s in migrate.discover(tmp_path)] == ["V002__a.sql", "V010__b.sql"]


def test_discover_rejects_bad_names(tmp_path):
    (tmp_path / "0001_create_runs.sql").write_text("x")
    with pytest.raises(migrate.MigrationError):
        migrate.discover(tmp_path)


def test_discover_rejects_duplicate_versions(tmp_path):
    (tmp_path / "V001__a.sql").write_text("x")
    (tmp_path / "V001__b.sql").write_text("x")
    with pytest.raises(migrate.MigrationError):
        migrate.discover(tmp_path)


def test_checksum_ignores_line_endings(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "V001__x.sql").write_bytes(b"SELECT 1;\nGO\n")
    (b / "V001__x.sql").write_bytes(b"SELECT 1;\r\nGO\r\n")
    assert migrate.discover(a)[0].checksum == migrate.discover(b)[0].checksum


# --- migrate -------------------------------------------------------------------

def test_first_run_applies_all_and_records_them(mig_dir):
    conn = FakeConn()
    applied = migrate.migrate(conn, directory=mig_dir)
    assert applied == ["V001__one.sql", "V002__two.sql"]
    assert set(conn.committed) == set(applied)
    assert len(conn.ddl) == 3


def test_second_run_changes_nothing(mig_dir):
    conn = FakeConn()
    migrate.migrate(conn, directory=mig_dir)
    ddl_before, recorded_before = list(conn.ddl), dict(conn.committed)
    assert migrate.migrate(conn, directory=mig_dir) == []
    assert conn.ddl == ddl_before
    assert conn.committed == recorded_before


def test_new_script_is_applied_alone(mig_dir):
    conn = FakeConn()
    migrate.migrate(conn, directory=mig_dir)
    (mig_dir / "V003__three.sql").write_text("CREATE TABLE dbo.D (x int);")
    assert migrate.migrate(conn, directory=mig_dir) == ["V003__three.sql"]


def test_edited_applied_script_is_an_error(mig_dir):
    conn = FakeConn()
    migrate.migrate(conn, directory=mig_dir)
    (mig_dir / "V001__one.sql").write_text("CREATE TABLE dbo.A (x int, y int);")
    with pytest.raises(migrate.MigrationError, match="edited"):
        migrate.migrate(conn, directory=mig_dir)


def test_failed_script_is_not_recorded(mig_dir):
    conn = FakeConn()
    conn.fail_on = "dbo.C"
    with pytest.raises(RuntimeError):
        migrate.migrate(conn, directory=mig_dir)
    assert set(conn.committed) == {"V001__one.sql"}


def test_dry_run_changes_nothing(mig_dir):
    conn = FakeConn(compat=150)
    assert migrate.migrate(conn, dry_run=True, directory=mig_dir) == ["V001__one.sql", "V002__two.sql"]
    assert conn.ddl == [] and conn.committed == {} and conn.compat == 150
    assert not conn.has_version_table


def test_preflight_failure_stops_before_any_ddl(mig_dir):
    conn = FakeConn(in_mb=600.0, storage=(1000.0, 0.0))
    with pytest.raises(preflight.PreflightError):
        migrate.migrate(conn, directory=mig_dir)
    assert conn.ddl == [] and not conn.has_version_table


# --- preflight -----------------------------------------------------------------

def test_compat_160_is_left_alone():
    conn = FakeConn(compat=160)
    assert preflight.check_compatibility(conn) is False
    assert preflight.SQL_SET_COMPAT not in conn.executed


def test_compat_150_is_set_to_160_outside_transaction():
    conn = FakeConn(compat=150)
    assert preflight.check_compatibility(conn) is True
    assert conn.compat == 160
    assert conn.autocommit is False  # restored


@pytest.mark.parametrize("db", ["ListmanagementDB", "Listmanagement_in", "listmanagement_filters"])
def test_compat_refuses_source_database(db):
    conn = FakeConn(compat=150, name=db)
    with pytest.raises(preflight.PreflightError):
        preflight.check_compatibility(conn)
    assert conn.compat == 150


@pytest.mark.parametrize("in_mb, reserved, used, ok", [
    (100.0, 1000.0, 800.0, True),    # free 200 == 2 x 100
    (100.0, 1000.0, 801.0, False),   # free 199 <  200
    (0.0, 10.0, 10.0, True),         # empty In database
])
def test_storage_boundary(in_mb, reserved, used, ok):
    conn = FakeConn(in_mb=in_mb, storage=(reserved, used))
    if ok:
        assert preflight.check_storage(conn).ok
    else:
        with pytest.raises(preflight.PreflightError, match="Not enough storage"):
            preflight.check_storage(conn)


def test_storage_without_stats_is_an_error():
    with pytest.raises(preflight.PreflightError):
        preflight.check_storage(FakeConn(storage=None))


def test_skip_storage_check(mig_dir):
    conn = FakeConn(in_mb=10_000.0, storage=(1.0, 1.0))
    assert migrate.migrate(conn, skip_storage=True, directory=mig_dir)


# --- connection ----------------------------------------------------------------

@pytest.mark.parametrize("db", ["ListmanagementDB", "Listmanagement_in", "LISTMANAGEMENT_FILTERS"])
def test_connection_refuses_source_databases(monkeypatch, db):
    monkeypatch.setenv("DATAENGINE_SQL_DATABASE", db)
    with pytest.raises(connection.ConfigError):
        connection.target_database()


def test_connection_string_uses_pipeline_login(monkeypatch):
    monkeypatch.setenv("DATAENGINE_SQL_SERVER", "example.database.windows.net")
    monkeypatch.delenv("DATAENGINE_SQL_DATABASE", raising=False)
    cs = connection.connection_string("pw")
    assert "UID=dataengine_pipeline;" in cs
    assert "DATABASE=Listmanagement_core;" in cs
    assert "Encrypt=yes" in cs
    assert "APP=dataengine-migrate" in cs
    assert "Application Name" not in cs  # ADO.NET keyword; ODBC rejects it


def test_connection_string_escapes_braces_in_password(monkeypatch):
    monkeypatch.setenv("DATAENGINE_SQL_SERVER", "example.database.windows.net")
    cs = connection.connection_string("a}b;c")
    assert "PWD={a}}b;c};" in cs
