# sql/migrations

Versioned DDL for `Listmanagement_core` only. Never change `ListmanagementDB`,
`Listmanagement_in` or `Listmanagement_filters`.

- Name files `V###__name.sql` (e.g. `V001__core_schema.sql`). The runner
  (`python -m sql.runner.migrate`) applies them in order and records each in
  `dbo.SchemaVersion`.
- Never edit a script that has been applied. Its checksum is recorded, and the
  runner will stop. Add the next `V###` script instead.
- Changes are additive and safe to re-run (`IF NOT EXISTS` / `IF OBJECT_ID(...) IS NULL`).
- Tables keep raw values next to corrected, derived or imputed ones.

See `docs/core_schema.md`.
