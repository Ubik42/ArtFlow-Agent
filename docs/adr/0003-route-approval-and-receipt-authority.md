# ADR 0003: Route approval and provider receipt authority

- Status: Accepted
- Date: 2026-08-25

## Context

The v0 approval gate authorizes a whole deterministic run plan. Multi-provider routing adds policy
fields that can change after planning: provider, model, input package, execution kind, privacy class
and cost class. Reusing an earlier approval after any of those fields changes would make the audit
trail misleading. A provider response also cannot be trusted as proof that the approved route ran;
ArtFlow must correlate it with the decision it authorized.

## Decision

`route-decision/1` is the authority for provider choice. Its approval fingerprint is a canonical
SHA-256 digest over the decision ID, scene package ID and hash, task, provider, model, execution
kind, privacy class and cost class. `approval-grant/1` authorizes exactly that fingerprint and may
expire. Any policy-sensitive change produces a different fingerprint and requires a new grant.

`provider-execution-receipt/1` is the normalized ArtFlow record of an execution outcome. It carries
the route decision ID and fingerprint, provider/model identity, timing, status and package-relative
artifact hashes. Provider-native IDs are evidence inputs, not the authority for ArtFlow state.
Successful receipts require artifacts; failed or cancelled receipts require a stable error code.

The current ComfyUI implementation is exposed to orchestration through `RecipeExecutionProvider`.
`ComfyRecipeProvider` is the first adapter. Reviewed recipe construction and Comfy transport remain
inside the adapter side of that seam; orchestration does not gain arbitrary graph mutation.

## Failure semantics

- A changed or expired approval fails closed before provider execution.
- Missing output cannot produce a successful normalized receipt.
- Receipt paths cannot escape the delivery package.
- Provider outages and protocol errors remain explicit failures until M4 introduces durable retry
  and fallback proposals.
- A fallback that changes provider, cost, privacy, model or input invalidates the old approval.

## Consequences

This adds three small cross-language contracts but avoids adopting a workflow framework. Hosted
providers can implement the same port later, and approval/receipt replay remains independent of
provider SDKs. Existing v0 receipts stay readable; migration to the normalized receipt is additive.
