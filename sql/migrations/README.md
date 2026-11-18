# sql/migrations

Versioned DDL for `Listmanagement_core` only. Never change `ListmanagementDB`,
`Listmanagement_in` or `Listmanagement_filters`.

- Name files in order, for example `0001_create_runs.sql`.
- Changes are additive and safe to re-run (`IF NOT EXISTS` / `IF OBJECT_ID(...) IS NULL`).
- Tables keep raw values next to corrected, derived or imputed ones.
