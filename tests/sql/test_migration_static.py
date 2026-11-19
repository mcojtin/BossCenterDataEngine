"""Static checks on the core-schema migration. No database needed."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from sql.runner.migrate import MIGRATIONS_DIR, discover, split_batches
from tools import gen_attr_ddl

REPO = Path(__file__).resolve().parents[2]
V001 = MIGRATIONS_DIR / "V001__core_schema.sql"
SAMPLE_CSV = REPO / "tests" / "sample_data" / "VerticalField.csv"

EXPECTED_TABLES = {
    "PipelineRun", "Person", "LeadEvent", "Contact", "Address",
    "MortgageAttr", "InsuranceAttr", "SolarAttr", "StudentAttr", "HomeOwnerAttr",
    "QualityFlag", "DNC", "RecordStatus", "DuplicateReport", "FieldMap",
    "Watermark", "OfferType",
}


def strip_comments(sql: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


@pytest.fixture(scope="module")
def sql() -> str:
    return V001.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(sql) -> str:
    return strip_comments(sql)


def created_tables(code: str) -> list[str]:
    return re.findall(r"CREATE\s+TABLE\s+dbo\.(\w+)", code, re.IGNORECASE)


def test_v001_is_first_migration():
    assert discover()[0].name == "V001__core_schema.sql"


def test_every_expected_table_is_created(code):
    tables = created_tables(code)
    assert len(tables) == len(set(tables)), "a table is created twice"
    assert set(tables) == EXPECTED_TABLES


def test_every_create_table_is_guarded(code):
    for table in created_tables(code):
        guard = rf"IF\s+OBJECT_ID\(N'dbo\.{table}',\s*N'U'\)\s+IS\s+NULL\s+BEGIN\s+CREATE\s+TABLE\s+dbo\.{table}\b"
        assert re.search(guard, code, re.IGNORECASE), f"CREATE TABLE dbo.{table} is not guarded"


def test_every_create_index_is_guarded(code):
    for name, table in re.findall(r"CREATE\s+(?:UNIQUE\s+)?(?:NONCLUSTERED\s+)?INDEX\s+(\w+)\s+ON\s+dbo\.(\w+)",
                                  code, re.IGNORECASE):
        guard = (rf"IF\s+NOT\s+EXISTS\s*\(SELECT\s+1\s+FROM\s+sys\.indexes\s+WHERE\s+name\s*=\s*N'{name}'"
                 rf"\s+AND\s+object_id\s*=\s*OBJECT_ID\(N'dbo\.{table}'\)\)\s+CREATE")
        assert re.search(guard, code, re.IGNORECASE), f"index {name} is not guarded"


@pytest.mark.parametrize("word", ["DROP", "DELETE", "TRUNCATE", "MERGE", "UPDATE", "ALTER"])
def test_no_destructive_or_altering_statements(code, word):
    assert not re.search(rf"\b{word}\b", code, re.IGNORECASE), f"{word} found in V001"


def test_no_reference_to_source_databases(sql):
    for db in ("ListmanagementDB", "Listmanagement_in", "Listmanagement_filters"):
        assert not re.search(rf"\b{db}\b", strip_comments(sql), re.IGNORECASE)


def test_no_three_part_names(code):
    # Only dbo.<table> and sys.<view> are allowed; nothing like OtherDb.dbo.Table.
    assert not re.search(r"\b\w+\.\w+\.\w+\b", code)


def test_value_source_check_on_attr_tables(code):
    for table in EXPECTED_TABLES:
        if table.endswith("Attr"):
            assert f"CK_{table}_ValueSource CHECK (ValueSource IN ('lead', 'enriched'))" in code


def test_generated_attr_block_matches_vertical_field(sql):
    expected = gen_attr_ddl.render_all(SAMPLE_CSV)
    start = sql.index(gen_attr_ddl.BEGIN_MARKER)
    end = sql.index(gen_attr_ddl.END_MARKER) + len(gen_attr_ddl.END_MARKER) + 1
    assert sql[start:end] == expected, "Attr tables drifted from VerticalField.csv; regenerate in a NEW migration"


def test_insurance_health_fields_are_excluded(sql):
    excluded = gen_attr_ddl.read_name_list(gen_attr_ddl.HEALTH_EXCLUDED_FILE)
    insurance = sql[sql.index("CREATE TABLE dbo.InsuranceAttr"):sql.index("CREATE TABLE dbo.SolarAttr")]
    cols = {c.lower() for c in re.findall(r"\[(\w+)\]", insurance)}
    assert not cols & excluded
    # Kept by decision (see config/fieldmaps/insurance_excluded_health.txt).
    assert {"uninsurable", "heightfeet", "heightinches", "weight", "smoker", "healthconditions", "recentconcern"} <= cols


def test_core_fields_not_repeated_in_attr_tables():
    core = gen_attr_ddl.read_name_list(gen_attr_ddl.CORE_COLUMNS_FILE)
    for vid, cols in gen_attr_ddl.attr_columns(SAMPLE_CSV).items():
        assert not {c.lower() for c, _ in cols} & core, f"vertical {vid} repeats a core column"


def test_script_splits_into_batches(sql):
    batches = split_batches(sql)
    assert len(batches) >= len(EXPECTED_TABLES)
    assert all(not re.match(r"^\s*GO\s*$", b, re.IGNORECASE) for b in batches)
