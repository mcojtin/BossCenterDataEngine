"""Database checks that run before any migration.

1. Compatibility level of the connected (core) database must be 160; it is
   set if not. Only the connected database is changed, never a source one.
2. The instance must have free storage of at least 2x the current size of
   Listmanagement_in (read from catalog views only).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .connection import SOURCE_DATABASES

log = logging.getLogger(__name__)

REQUIRED_COMPATIBILITY = 160
STORAGE_FACTOR = 2
IN_DATABASE = "Listmanagement_in"

SQL_CURRENT_DB = "SELECT DB_NAME(), compatibility_level FROM sys.databases WHERE database_id = DB_ID();"
SQL_SET_COMPAT = f"ALTER DATABASE CURRENT SET COMPATIBILITY_LEVEL = {REQUIRED_COMPATIBILITY};"
# Used pages across every table and index in the In database, in MB.
SQL_IN_SIZE_MB = f"SELECT CAST(COALESCE(SUM(used_pages), 0) * 8 / 1024.0 AS float) FROM {IN_DATABASE}.sys.allocation_units;"
# Latest Managed Instance storage sample.
SQL_INSTANCE_STORAGE_MB = (
    "SELECT TOP (1) CAST(reserved_storage_mb AS float), CAST(storage_space_used_mb AS float) "
    "FROM master.sys.server_resource_stats ORDER BY end_time DESC;"
)


class PreflightError(RuntimeError):
    pass


@dataclass
class StorageResult:
    in_data_mb: float
    free_mb: float

    @property
    def required_mb(self) -> float:
        return self.in_data_mb * STORAGE_FACTOR

    @property
    def ok(self) -> bool:
        return self.free_mb >= self.required_mb


def check_compatibility(conn) -> bool:
    """Ensure compatibility_level is 160. Returns True if it had to be changed."""
    cur = conn.cursor()
    db_name, level = cur.execute(SQL_CURRENT_DB).fetchone()
    if db_name.lower() in SOURCE_DATABASES:
        raise PreflightError(f"Connected to source database {db_name!r}; refusing to continue.")
    if level == REQUIRED_COMPATIBILITY:
        log.info("compatibility_level of %s is %s: ok", db_name, level)
        return False
    log.warning("compatibility_level of %s is %s; setting to %s", db_name, level, REQUIRED_COMPATIBILITY)
    # ALTER DATABASE cannot run inside a user transaction.
    previous = conn.autocommit
    conn.autocommit = True
    try:
        cur.execute(SQL_SET_COMPAT)
    finally:
        conn.autocommit = previous
    _, level = cur.execute(SQL_CURRENT_DB).fetchone()
    if level != REQUIRED_COMPATIBILITY:
        raise PreflightError(f"compatibility_level is still {level} after ALTER DATABASE.")
    return True


def measure_storage(conn) -> StorageResult:
    cur = conn.cursor()
    (in_mb,) = cur.execute(SQL_IN_SIZE_MB).fetchone()
    row = cur.execute(SQL_INSTANCE_STORAGE_MB).fetchone()
    if row is None:
        raise PreflightError("master.sys.server_resource_stats returned no rows; cannot check storage.")
    reserved_mb, used_mb = row
    return StorageResult(in_data_mb=float(in_mb or 0), free_mb=float(reserved_mb) - float(used_mb))


def check_storage(conn) -> StorageResult:
    result = measure_storage(conn)
    msg = (
        f"free storage {result.free_mb:,.0f} MB; {IN_DATABASE} data {result.in_data_mb:,.0f} MB; "
        f"need {result.required_mb:,.0f} MB ({STORAGE_FACTOR}x)"
    )
    if not result.ok:
        raise PreflightError("Not enough storage: " + msg)
    log.info("storage ok: %s", msg)
    return result


def run(conn, skip_storage: bool = False) -> None:
    check_compatibility(conn)
    if skip_storage:
        log.warning("storage check SKIPPED by --skip-storage-check")
    else:
        check_storage(conn)
