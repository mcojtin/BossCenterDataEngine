# ai_review

A standalone job that checks names with the Claude API. It is separate from the
main pipeline.

- It sends only `first_name`, `last_name` and `email`. No other fields.
- The API key comes from Windows Credential Manager or Azure Key Vault.
- Results are stored next to the original values and never overwrite them.
- It writes by run ID and skips records already reviewed.
