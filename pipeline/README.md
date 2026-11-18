# pipeline

Python row-by-row steps that run on the Windows VM: standardize, vertical rules,
address and quality.

- Connect with the `dataengine_pipeline` login only.
- Read secrets from Windows Credential Manager or Azure Key Vault, never from code.
- Store corrected, derived or imputed values next to the originals.
- Every step writes by run ID and skips work already done.
