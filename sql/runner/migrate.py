"""Apply sql/migrations/V###__*.sql to Listmanagement_core, in order, once each.

    python -m sql.runner.migrate [--dry-run] [--skip-storage-check]

- Runs the database checks (preflight) first.
- Records each applied script in dbo.SchemaVersion with a SHA-256 checksum.
- Skips scripts already recorded; stops if an applied script was edited.
- Each script runs in one transaction and is recorded only if it succeeds.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import preflight

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BOOTSTRAP_SQL = Path(__file__).resolve().parent / "schema_version.sql"
SCRIPT_NAME = re.compile(r"^V(\d{3})__[a-z0-9_]+\.sql$")
GO_LINE = re.compile(r"^\s*GO\s*;?\s*$", re.IGNORECASE)


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Script:
    version: int
    name: str
    path: Path

    @property
    def text(self) -> str:
        # Normalise line endings so a Windows checkout has the same checksum.
        return self.path.read_text(encoding="utf-8").replace("\r\n", "\n")

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def discover(directory: Path = MIGRATIONS_DIR) -> list[Script]:
    scripts = []
    for path in directory.glob("*.sql"):
        m = SCRIPT_NAME.match(path.name)
        if not m:
            raise MigrationError(f"Bad migration file name {path.name!r}; expected V###__name.sql")
        scripts.append(Script(int(m.group(1)), path.name, path))
    scripts.sort(key=lambda s: s.version)
    versions = [s.version for s in scripts]
    if len(versions) != len(set(versions)):
        raise MigrationError(f"Duplicate migration version numbers in {directory}")
    return scripts


def split_batches(sql: str) -> list[str]:
    """Split a script on lines that contain only GO, dropping empty batches."""
    batches, current = [], []
    for line in sql.splitlines():
        if GO_LINE.match(line):
            batches.append("\n".join(current))
            current = []
        else:
            current.append(line)
    batches.append("\n".join(current))
    return [b for b in batches if _has_code(b)]


def _has_code(batch: str) -> bool:
    return any(line.strip() and not line.strip().startswith("--") for line in batch.splitlines())


def applied_checksums(conn) -> dict[str, str]:
    cur = conn.cursor()
    exists = cur.execute("SELECT OBJECT_ID(N'dbo.SchemaVersion', N'U');").fetchone()[0]
    if exists is None:
        return {}
    return {name: checksum.strip() for name, checksum in cur.execute(
        "SELECT ScriptName, Checksum FROM dbo.SchemaVersion;").fetchall()}


def pending(scripts: list[Script], applied: dict[str, str]) -> list[Script]:
    todo = []
    for s in scripts:
        if s.name in applied:
            if applied[s.name] != s.checksum:
                raise MigrationError(
                    f"{s.name} was already applied but has been edited since "
                    f"(checksum {applied[s.name][:12]} != {s.checksum[:12]}). "
                    "Never edit an applied migration; add a new V### script instead."
                )
            continue
        todo.append(s)
    return todo


def bootstrap(conn) -> None:
    cur = conn.cursor()
    for batch in split_batches(BOOTSTRAP_SQL.read_text(encoding="utf-8")):
        cur.execute(batch)
    conn.commit()


def apply(conn, script: Script) -> int:
    started = time.monotonic()
    cur = conn.cursor()
    try:
        for batch in split_batches(script.text):
            cur.execute(batch)
        ms = int((time.monotonic() - started) * 1000)
        cur.execute(
            "INSERT INTO dbo.SchemaVersion (ScriptName, Checksum, DurationMs) VALUES (?, ?, ?);",
            script.name, script.checksum, ms,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return ms


def migrate(conn, *, dry_run: bool = False, skip_storage: bool = False,
            directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Run preflight and apply pending scripts. Returns the names applied (or pending, if dry_run)."""
    scripts = discover(directory)
    if dry_run:
        todo = pending(scripts, applied_checksums(conn))
        for s in todo:
            log.info("would apply %s", s.name)
        return [s.name for s in todo]

    preflight.run(conn, skip_storage=skip_storage)
    bootstrap(conn)
    todo = pending(scripts, applied_checksums(conn))
    if not todo:
        log.info("nothing to apply; schema is up to date")
    for s in todo:
        ms = apply(conn, s)
        log.info("applied %s in %d ms", s.name, ms)
    return [s.name for s in todo]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="list pending scripts; change nothing")
    parser.add_argument("--skip-storage-check", action="store_true", help="skip the 2x storage check (logged)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from .connection import connect

    conn = connect()
    try:
        migrate(conn, dry_run=args.dry_run, skip_storage=args.skip_storage_check)
    except (MigrationError, preflight.PreflightError) as exc:
        log.error("%s", exc)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
