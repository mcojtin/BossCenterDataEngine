"""Generate the per-vertical *Attr table DDL from VerticalField.csv.

This is a developer tool. Its output is pasted into a migration script once;
it is never run at deploy time. tests/sql/test_migration_static.py checks that
the migration still matches what this tool produces.

    python -m tools.gen_attr_ddl [path/to/VerticalField.csv]
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "tests" / "sample_data" / "VerticalField.csv"
CORE_COLUMNS_FILE = REPO / "config" / "fieldmaps" / "core_columns.txt"
HEALTH_EXCLUDED_FILE = REPO / "config" / "fieldmaps" / "insurance_excluded_health.txt"

# Active verticals in v1: VerticalID -> table name prefix.
ACTIVE_VERTICALS: dict[int, str] = {
    1: "Mortgage",
    4: "Insurance",
    5: "Solar",
    7: "Student",
    12: "HomeOwner",
}
INSURANCE_VERTICAL_ID = 4

BEGIN_MARKER = "-- BEGIN GENERATED ATTR TABLES (tools/gen_attr_ddl.py)"
END_MARKER = "-- END GENERATED ATTR TABLES"


def read_name_list(path: Path) -> set[str]:
    """Read a one-name-per-line file, ignoring blanks and # comments. Lower-cased."""
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.add(line.lower())
    return names


def sql_type(field_type: str, max_length: str) -> str:
    """Map a VerticalField type to the SQL type used by the In tables."""
    if field_type == "Number":
        return "decimal(14,3)"
    if field_type == "Date":
        return "datetime2(3)"
    if field_type == "Text":
        length = int(max_length or 0)
        return f"varchar({length})" if length > 0 else "varchar(255)"
    raise ValueError(f"Unknown FieldType {field_type!r}")


def attr_columns(csv_path: Path = DEFAULT_CSV) -> dict[int, list[tuple[str, str]]]:
    """Return {VerticalID: [(column, sql_type), ...]} for every active vertical."""
    core = read_name_list(CORE_COLUMNS_FILE)
    health = read_name_list(HEALTH_EXCLUDED_FILE)
    result: dict[int, list[tuple[str, str]]] = {v: [] for v in ACTIVE_VERTICALS}
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: int(r["FieldID"]))
    for row in rows:
        vid = int(row["VerticalID"])
        name = row["FieldName"].strip()
        if vid not in result or name.lower() in core:
            continue
        if vid == INSURANCE_VERTICAL_ID and name.lower() in health:
            continue
        result[vid].append((name, sql_type(row["FieldType"], row["MaxLength"])))
    return result


def render_table(prefix: str, columns: list[tuple[str, str]]) -> str:
    table = f"{prefix}Attr"
    lines = [
        f"IF OBJECT_ID(N'dbo.{table}', N'U') IS NULL",
        "BEGIN",
        f"    CREATE TABLE dbo.{table} (",
        "        LeadEventID   bigint       NOT NULL,",
        "        ValueSource   varchar(10)  NOT NULL,",
        "        RunID         bigint       NOT NULL,",
        f"        LoadedAt      datetime2(3) NOT NULL CONSTRAINT DF_{table}_LoadedAt DEFAULT SYSUTCDATETIME(),",
    ]
    for name, typ in columns:
        lines.append(f"        [{name}] {typ} NULL,")
    lines += [
        f"        CONSTRAINT PK_{table} PRIMARY KEY (LeadEventID, ValueSource),",
        f"        CONSTRAINT CK_{table}_ValueSource CHECK (ValueSource IN ('lead', 'enriched')),",
        f"        CONSTRAINT FK_{table}_LeadEvent FOREIGN KEY (LeadEventID) REFERENCES dbo.LeadEvent (LeadEventID),",
        f"        CONSTRAINT FK_{table}_PipelineRun FOREIGN KEY (RunID) REFERENCES dbo.PipelineRun (RunID)",
        "    );",
        "END;",
        "GO",
    ]
    return "\n".join(lines)


def render_all(csv_path: Path = DEFAULT_CSV) -> str:
    cols = attr_columns(csv_path)
    parts = [BEGIN_MARKER]
    for vid, prefix in ACTIVE_VERTICALS.items():
        parts.append(f"-- {prefix} (VerticalID {vid})")
        parts.append(render_table(prefix, cols[vid]))
    parts.append(END_MARKER)
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    sys.stdout.write(render_all(path))
