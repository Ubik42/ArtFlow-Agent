# M3-S5 hosted provider privacy-cost boundary

Date: 2026-08-25  
Evidence level: A2 — recorded hosted HTTP contract and failure injection  
Real credential, paid provider call or image generation used: no

## Proven behavior

Hosted execution now uses the same `ProviderExecutionCoordinator`, append-only event ledger,
unknown-completion semantics and normalized `ProviderExecutionReceipt` as local execution. A
hosted contract attestation has a distinct schema and explicit `fixture_only=true`, so recorded
compatibility cannot be confused with live-provider readiness.

`HostedRequestCompiler` reads only authoritative run state and emits a redacted allowlist:

- approved art goal, preserve/prohibit constraints and output dimensions;
- content-hashed `reference_image`, depth, world-normal and object-ID passes explicitly required by
  the route;
- route, provider/model, privacy and Scene Package fingerprints needed for verification.

It excludes source scene names, camera transforms, region inventories and protected masks. The
HTTP payload has a closed top-level field set and contains no raw Scene Package document.

The visible `HostedAuthorityPacket` binds the complete compiled request, remote privacy class and
maximum approved cost under an HMAC signature. It expires and is atomically consumed once in
SQLite before submit. Missing credentials, absent/forged/stale authority, privacy drift and cost
drift fail closed.

The adapter implements the durable provider port:

```text
lookup(idempotency key) -> none | running | terminal
submit(idempotency key, redacted request) -> provider request ID
fetch_artifact(provider request ID, receipt path) -> independently hashed bytes
```

A stateful recorded HTTP fixture proved accepted submission, running observation, terminal success,
artifact download and independent SHA-256 verification through the real coordinator. Separate
fixtures bounded provider HTTP errors, malformed responses and response identity drift. JSON
Schemas were generated for the hosted request and authority packet.

## Verification

```text
python -m ruff check <hosted boundary, attestation, runtime, projection, schemas and focused tests>
All checks passed

python -m pytest <hosted, provider ledger and attestation tests> -q
12 passed in 1.36s

powershell -ExecutionPolicy Bypass -File scripts/validate.ps1 -Tier quick
63 passed in 3.81s

python scripts/export_contract_schemas.py --check
generated schemas synchronized
```

## Evidence ceiling

This proves a vendor-neutral recorded provider boundary. It does not prove compatibility with a
currently selected commercial API, live credential readiness, actual price, image quality or a
paid generation. Those claims require an explicit provider decision and user-authorized live run.
