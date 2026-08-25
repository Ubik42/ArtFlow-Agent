# ADR 0002: compile a provider-neutral scene constraint package

Status: accepted  
Date: 2026-08-25

## Context

Prompts and ComfyUI workflows are provider-specific. The product needs to preserve camera, scene
structure, editable regions and source provenance while routing the same approved intent through
local or hosted image systems.

## Decision

Introduce `scene-constraint-package/1` as the boundary between a DCC/engine and ArtFlow. It requires
camera data plus beauty, depth, world-normal and object-ID passes. Every artifact is package-relative
and content-addressed. Region constraints refer to semantic object IDs and state whether those
objects are protected or editable.

Provider adapters compile this package into their own calls. They may omit controls the provider
does not support only if routing policy declares the degradation and obtains any required approval.
The original package is immutable and retained as a receipt ingredient.

## Consequences

- Unreal capture can be developed independently from provider execution.
- Local and hosted results can be compared against identical spatial facts.
- A model upgrade does not invalidate the scene contract.
- Cross-language JSON Schema compatibility becomes a milestone gate.

