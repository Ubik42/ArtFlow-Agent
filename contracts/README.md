# 跨语言合同

M7 新增三套三维场景合同：

- `scene-digital-twin.v1.schema.json`：Unreal 三维事实；
- `scene-change-plan.v1.schema.json`：受限灯光/PCG 操作 DAG；
- `scene-dry-run-receipt.v1.schema.json`：零写入 dry-run 证明。

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

Verify the same scene fixture in the non-Python consumers:

```powershell
Set-Location web
npm run verify:contracts
Set-Location ..
.\scripts\verify_unreal_contract.ps1
```

Ajv is used only by the TypeScript contract check so the exported schema remains the authority;
`tsx` is only its development-time runner. The C++ fixture compiles against RapidJSON shipped with
the local Unreal installation and does not create or modify an Unreal project.

Schema IDs are compatibility boundaries. Additive implementation changes do not require a new ID;
removing fields, changing types, or changing validation semantics requires a new version and a
migration note.

The route decision's `approval_fingerprint()` binds approval to the scene package, task, provider,
model, execution kind, privacy class and cost class. Any change to those fields invalidates the
previous grant. Provider receipts carry the same fingerprint so a result cannot be attached to a
different approved route.

The hosted image-edit request is a deliberately redacted boundary: only approved art direction,
dimensions and allowlisted content-hashed passes may leave the machine. Its one-use authority packet
binds that complete request to the visible privacy class and maximum approved cost before transport
access.

The provider comparison plan binds two independently authorized child runs to one Scene Package and
art intent. Its human-owner authorization excludes Unreal return authority, while the comparison
manifest normalizes both outcomes without claiming an automatic or human-selected winner.
