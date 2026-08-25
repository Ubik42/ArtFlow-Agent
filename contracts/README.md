# Cross-language contracts

This directory contains generated JSON Schemas used at process and repository boundaries. The
authoritative Python models live in `src/artflow_agent/contracts`.

Regenerate after intentional contract changes:

```powershell
.\.venv\Scripts\python scripts\export_contract_schemas.py
```

Verify generated files are synchronized without writing:

```powershell
.\.venv\Scripts\python scripts\export_contract_schemas.py --check
```

Schema IDs are compatibility boundaries. Additive implementation changes do not require a new ID;
removing fields, changing types, or changing validation semantics requires a new version and a
migration note.

