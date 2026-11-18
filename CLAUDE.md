# CLAUDE.md

## Purpose

This repo is a lead-data cleanup pipeline. It runs alongside today's ListManagement
process and does not replace it: it reads from the existing ListManagement databases
and writes cleaned, deduplicated, publish-ready records to `Listmanagement_core`.

## Architecture

| Where | What | Steps |
|---|---|---|
| SQL Managed Instance | Set-based steps (T-SQL stored procedures) | dedupe, identity, DNC, publish |
| Windows VM (Python) | Row-by-row steps | standardize, vertical rules, address, quality |
| Separate job (Python) | AI name check via the Claude API | name review |

## Rules

1. **Don't change today's process.** Read only from `ListmanagementDB`, `Listmanagement_in`
   and `Listmanagement_filters`. Write only to `Listmanagement_core`.
2. **Use the `dataengine_pipeline` login.** It can only read the existing databases. Never
   use an admin login in code.
3. **Split the work by engine.** SQL on the Managed Instance does the set-based steps (dedupe,
   identity, DNC, publish). Python on the Windows VM does the row-by-row steps (standardize,
   vertical rules, address, quality).
4. **Never delete a record.** Duplicates and blocked records are kept, linked or flagged,
   with a reason.
5. **Keep raw values.** A corrected, derived or imputed value is stored next to the original,
   never in place of it.
6. **Every step can be re-run safely.** Each step writes by run ID and skips work already done.
7. **The AI name check is a separate job.** It calls the Claude API and sends only
   `first_name`, `last_name` and `email`. No other fields leave the network.
8. **No passwords or API keys in code.** Read them from Windows Credential Manager or
   Azure Key Vault.
9. **Every change includes tests and docs.** Add tests in `tests/` and a page in `docs/`
   that explains the step.
10. **Plan first.** Show a plan and wait for approval before writing code.
11. **Active verticals in v1:** Mortgage, Insurance, Solar, Student, HomeOwner. Insurance
    health fields stay out of the core.

## Data boundaries (quick reference)

- **Read only:** `ListmanagementDB`, `Listmanagement_in`, `Listmanagement_filters`
- **Write:** `Listmanagement_core` only
- **Login:** `dataengine_pipeline` only
- **Secrets:** Windows Credential Manager or Azure Key Vault only

## Repo layout

- `sql/migrations/`: versioned, re-runnable DDL for `Listmanagement_core`
- `sql/procs/`: stored procedures for dedupe, identity, DNC and publish
- `config/fieldmaps/`: mappings from source fields to core fields
- `config/rules/`: rules for each vertical
- `pipeline/`: Python row-by-row steps
- `ai_review/`: standalone AI name-check job
- `sales_mcp/`: counts-only MCP connector for sales reps in Claude Desktop (numbers only, never records)
- `tests/`: tests for every step
- `docs/`: one page per step

## Definition of done

A change is done when it has:

- an approved plan
- code that follows the rules above
- tests in `tests/`
- a page in `docs/`
