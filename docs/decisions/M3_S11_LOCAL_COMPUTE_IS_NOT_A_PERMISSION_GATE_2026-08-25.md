# M3-S11 decision — development is not a permission workflow

Date: 2026-08-25

## Decision

ArtFlow-owned local ComfyUI/GPU execution, Codex built-in image generation, candidate selection and
local portfolio delivery are ordinary autonomous development work. They do not require the user to
repeatedly authorize uploads, queueing, generation, selection or packaging.

The earlier local `ComfyAuthorityGrant`, signer and consumed-grant database conflated two concerns:

1. whether a request is technically safe, bounded and reproducible; and
2. whether the user must grant permission for the project to perform it.

Only the first concern belongs in this project. Safety comes from verified Scene Package hashes,
reviewed recipes, allowlisted slots, deterministic routing, live dependency attestation,
durable-before-side-effect reservation, idempotency identity, independent evaluation and receipt
verification. These are truth and integrity checks, not permission prompts.

The portfolio's hosted comparison path uses Codex's built-in GPT Image 2 capability during
development. It does not require `OPENAI_API_KEY`, a direct paid API call or a user cost approval.
The earlier OpenAI API adapter remains historical/optional engineering evidence, not the main demo
path.

Historical M3-S4/M3-S8 evidence remains an honest record of the superseded design rather than being
rewritten. Current goal state and this decision take precedence for continued development.
