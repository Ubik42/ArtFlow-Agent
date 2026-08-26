# M3-S4 reviewed ComfyUI compiler and authority boundary

Date: 2026-08-25  
Evidence level: A2 — deterministic compiler and recorded HTTP boundary  
Real ComfyUI upload, queue, GPU generation or hosted call used: no

## Proven behavior

`ComfyWorkflowCompiler` accepts only repository-bundled, versioned recipe templates. It resolves
typed slots through the existing recipe validator and binds the compiled workflow to the persisted
execution reservation, approved route fingerprint, verified Scene Package archive and source pass
hash, supported environment attestation, recipe version and workflow SHA-256.

Compiler-owned source and output paths prevent model-generated filesystem or ComfyUI path values.
Route dimensions must exactly match the approved intent, prompt strings are bounded, and stale
execution, attestation, recipe or scene facts fail before transport access.

`AuthorityGatedComfyAdapter` is closed by default. Upload and queue require an externally signed
HMAC grant bound to the exact compiled request. The grant is atomically consumed in SQLite before
the first network side effect; forged, expired and replayed grants fail. The issuer is a separate
controller-side type and is not part of the Agent capability surface.

A recorded `httpx.MockTransport` fixture exercised the exact ComfyUI boundary sequence:

```text
POST /upload/image
POST /prompt
GET /history/<prompt-id>
GET /view
```

Terminal history is normalized into the shared provider receipt contract and output bytes are
hashed before the receipt is returned. This uses the same receipt shape as the crash-safe execution
ledger built in M3-S3.

## Verification

```text
python -m ruff check <Comfy gateway, compiler, authority adapter and focused tests>
All checks passed

python -m pytest <Comfy authority, gateway and execution-ledger tests> -q
10 passed in 0.56s

powershell -ExecutionPolicy Bypass -File scripts/validate.ps1 -Tier quick
57 passed in 2.28s
```

## Evidence ceiling

This proves request compilation, authority isolation, recorded HTTP compatibility and receipt
normalization. It does not prove that the reviewed workflow executes successfully on the real RTX
4080 environment; that remains behind explicit user authorization.
