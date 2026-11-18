# sales_mcp

A counts-only MCP connector. It lets the 3 sales reps ask Claude Desktop for
estimated lead counts now, while the clean core is being built.

- It returns numbers only, never records or any field values.
- It is read only and never writes to any database.
- It connects with the `dataengine_pipeline` login only.
- Credentials come from Windows Credential Manager or Azure Key Vault.
