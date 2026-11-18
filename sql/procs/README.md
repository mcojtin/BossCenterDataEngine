# sql/procs

T-SQL stored procedures for the set-based steps that run on the Managed Instance:
dedupe, identity, DNC and publish.

- Each procedure takes a run ID, writes by run ID and skips work already done.
- Nothing is deleted. Duplicates and blocked records are linked or flagged, with a reason.
- Procedures read only from the source databases and write only to `Listmanagement_core`.
