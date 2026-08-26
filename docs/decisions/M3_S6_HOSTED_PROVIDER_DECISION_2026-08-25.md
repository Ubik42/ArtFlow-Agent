# M3-S6 hosted image provider decision

Decision date: 2026-08-25  
Status: selected for adapter implementation; live execution not authorized  
Selected provider/model: OpenAI Images API, `gpt-image-2-2026-04-21`

## Decision

Use the synchronous `POST /v1/images/edits` endpoint with the fixed
`gpt-image-2-2026-04-21` snapshot for the one-provider portfolio comparison. The request will send
one verified beauty PNG plus approved art direction. Depth, world-normal and object-ID passes remain
local evaluation evidence and must not be uploaded.

This selection does not authorize a call. The machine-readable dossier remains
`authorization_state=awaiting_user`, does not inspect `OPENAI_API_KEY`, and caps the proposed run at
one 1280×720 medium-quality PNG with a user-approved ceiling of USD 0.25.

## Current official comparison

| Decision fact | OpenAI GPT Image 2 | Google Gemini 3.1 Flash Image |
| --- | --- | --- |
| Current model | OpenAI calls GPT Image 2 its state-of-the-art generation/editing model and publishes fixed snapshot `gpt-image-2-2026-04-21`. | Google calls `gemini-3.1-flash-image` its high-efficiency current image model; the model page identifies it as stable. |
| Edit inputs | Images API supports `/v1/images/edits`, multiple image inputs and an optional mask. GPT Image 2 always processes image inputs at high fidelity. | Interactions API accepts multiple inline images and supports conversational editing, 0.5K–4K output and many aspect ratios. |
| Proposed-size fit | Arbitrary sizes are accepted when both edges are multiples of 16, total pixels are 655,360–8,294,400 and aspect ratio is at most 3:1. 1280×720 satisfies these rules. | Official output control is expressed as aspect ratio plus 0.5K/1K/2K/4K size, so exact 1280×720 output is not documented. |
| Price evidence | Published token rates are $8/M image-input tokens and $30/M image-output tokens. The guide lists medium 1024² output at $0.053, excluding inputs; exact 1280×720 total is not fixed in advance. | Paid standard lists $0.50/M input tokens and about $0.067 per 1K image output. |
| Default data posture | API data is not used for training. Images endpoints have no application-state retention, but abuse-monitoring logs may retain content for up to 30 days. GPT Image 2 is ZDR-compatible only when the organization is approved/configured. | Paid content is not used to improve products. Interactions are stored by default for 55 days, configurable to 7/14/28/55; `store=false` disables state but is incompatible with background execution. ZDR requires separate project approval/configuration. |
| Provenance | OpenAI states API-generated images include C2PA Content Credentials and SynthID, directly supporting ArtFlow's later independent C2PA verification milestone. | Google states all generated images include SynthID; the reviewed Gemini API docs do not promise a C2PA manifest. |
| Recovery surface | Images edit is synchronous and returns base64 output. No client idempotency-key or job lookup is documented in the reviewed Images API guide/reference. | Interactions supports background status plus get/cancel/delete by provider ID, but no client idempotency key or lookup by client label is documented. Background recovery requires stored interaction state. |

Primary sources:

- [OpenAI GPT Image 2 model](https://developers.openai.com/api/docs/models/gpt-image-2)
- [OpenAI image generation/editing guide](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data)
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
- [OpenAI C2PA and SynthID](https://help.openai.com/en/articles/8912793-c2pa-in-images)
- [Gemini image generation guide](https://ai.google.dev/gemini-api/docs/image-generation)
- [Gemini 3.1 Flash Image model](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-image)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini Interactions state and retention](https://ai.google.dev/gemini-api/docs/interactions-overview)
- [Gemini Interactions API reference](https://ai.google.dev/api/interactions-api-v1)

## Why OpenAI for this demo

The exact 16:9 output, fixed model snapshot, high-fidelity edit input and C2PA output claim fit the
portfolio proof better than Gemini's lower price and richer stateful interaction surface. OpenAI's
Images endpoint also avoids application-state storage by default. The decision conservatively uses
`provider_retained`, because ZDR eligibility is not evidence that this user's organization has ZDR
enabled and default abuse-monitoring retention can be up to 30 days.

Gemini remains a credible later adapter, especially if multi-turn editing or provider-side
background status becomes more valuable than exact output dimensions and C2PA. It is not included
in the live demo now, avoiding a decorative third provider and extra spend.

## Provider-specific mapping

| ArtFlow fact | OpenAI Images field / evidence |
| --- | --- |
| fixed provider/model | multipart `model=gpt-image-2-2026-04-21` |
| verified visual input | one `image[]` part containing only the content-hash-verified beauty PNG |
| approved art direction | one bounded `prompt` assembled from goal, preserve and prohibit constraints |
| output contract | `n=1`, `size=1280x720`, `quality=medium`, `output_format=png` |
| mask | omitted for the initial scene-direction run because the current package has no verified editable mask |
| result | decode `data[0].b64_json`, hash bytes independently, then build `ProviderExecutionReceipt` |
| correlation | capture the provider `x-request-id` response header when present; never invent a job ID |
| cost | record returned token usage when available; compare with the USD 0.25 approval ceiling after the call |
| provenance | preserve returned PNG bytes before any conversion, then independently inspect C2PA in M6 |

The Images API has no documented lookup by ArtFlow's idempotency key. Consequently, a disconnect
after the request body was sent but before a complete response is `completion_unknown`. The Agent
must consume the one-use authority before transport, must not submit again automatically and must
escalate to the human owner. A fresh grant is not proof that the first call did not execute.

OpenAI's guide says retries are appropriate for transient 429/5xx errors. ArtFlow narrows that rule:
automatic retry is allowed only when transport evidence proves the request was rejected before
inference; ambiguous failures remain non-retriable without a new human decision.

## Exact authorization boundary

The proposed live demo consists of three separately unauthorized actions:

1. local ComfyUI: upload the verified beauty pass, queue `composition-preserving-v1` once on the
   attested RTX 4080 runtime, reconcile history, download and hash one PNG;
2. hosted OpenAI: send only the verified beauty PNG and bounded art direction to one synchronous
   `gpt-image-2-2026-04-21` edit, maximum approved cost USD 0.25;
3. Unreal: only after separate Unreal Bridge authorization, return a human-adopted PNG as a review
   asset—not as a claimed final 3D asset.

No depth EXR, world-normal EXR, object-ID PNG, scene name, object/region inventory, camera transform,
raw Scene Package JSON or secret value may enter the hosted request.

## Unresolved before execution

- The current package is a fixture, not a real Unreal capture.
- `OPENAI_API_KEY` presence and organization verification have not been inspected.
- ZDR configuration is unknown, so the approval must assume up to 30-day provider retention.
- Exact input-token cost is unknown until inputs are measured; USD 0.25 is an ArtFlow policy ceiling,
  not a provider-enforced precharge cap.
- Current routing incorrectly treats depth, world-normal and object-ID evidence as provider controls,
  even though the reviewed local recipe and hosted API do not consume them as typed controls. This
  must be corrected before a real route is approved.
- Unreal Bridge creation/write remains separately unauthorized.
