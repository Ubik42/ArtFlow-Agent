# M3-S7 truthful controls and recorded OpenAI Images adapter

Date: 2026-08-25  
Evidence level: A2 — reviewed provider mapping plus recorded HTTP fixtures  
Credential inspection, upload, generation or paid call used: no

## Result

`RouteExecutionIntent` now separates `required_controls`, which a selected adapter actually sends,
from `evaluation_evidence`, which remains local for the later tribunal. For the current scene task,
only the beauty image is a generation control; depth, world-normal and object-ID are evaluator
evidence. Mask is added only for a masked-refinement task with a verified editable mask.

The two reviewed Comfy recipes now declare their consumed controls. Local capability attestation
fails closed when a recipe consumes a control omitted by its model manifest. The bundled route
candidates therefore no longer claim that the existing FLUX workflow consumes depth, normals or
object IDs.

## Exact OpenAI boundary

`OpenAIImagesAdapter` implements only the documented synchronous surface selected in M3-S6:

- `POST /v1/images/edits`;
- fixed model `gpt-image-2-2026-04-21`;
- exactly one content-hash-verified `image[]` beauty PNG;
- bounded goal/preserve/prohibit prompt;
- `n=1`, exact approved size, `quality=medium`, `output_format=png`;
- no invented idempotency header, asynchronous job, or provider lookup;
- exactly one base64 PNG response and required `x-request-id` correlation;
- decoded bytes are independently hashed and preserved without conversion for later C2PA checks.

The one-use privacy/cost authority is consumed before transport. A timeout, network disconnect, or
malformed successful response raises `ProviderCompletionUnknown`; the durable coordinator now
persists that state directly from a reserved execution, and subsequent reconciliation cannot submit
again. Explicit provider errors, missing credential/authority, auxiliary pass upload, output count
drift, identity drift, bad base64 and non-PNG bytes all fail closed.

## Verification

```text
python -m pytest -q
69 passed in 2.69s

python -m pytest -q tests/test_openai_images.py tests/test_provider_execution.py \
  tests/test_routing.py tests/test_hosted_execution.py
21 passed in 1.13s

ruff check <M3-S7 changed Python files>
All checks passed

python scripts/export_contract_schemas.py
generated schemas synchronized
```

The repository-wide Ruff scan also observed three pre-existing import-order findings in the goal
validator scripts. They are outside this slice and do not affect the 69 passing tests or targeted
M3-S7 lint gate.

## Evidence ceiling

This proves request construction, authority consumption, response normalization and non-retry
policy against recorded transport fixtures. It does not prove that a credential exists, that the
live API accepts the request, exact billing, output quality, provider-side provenance content, or a
real two-provider run. No secret was read and no network request reached OpenAI.
