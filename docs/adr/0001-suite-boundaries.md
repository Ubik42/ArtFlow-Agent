# ADR 0001: keep product repositories separate and integrate by contracts

Status: accepted  
Date: 2026-08-25

## Context

ArtFlow Agent, ComfyUI Production Nodes and the AIToolTA host tools solve adjacent problems but have
different installation and release boundaries. A physical merge would couple a standalone local
application, a ComfyUI custom-node package and future Unreal editor code. It would also duplicate
the mature Agent reliability work already demonstrated by `verified-art-pipeline-agent`.

## Decision

- ArtFlow Agent remains the flagship application repository.
- ComfyUI Production Nodes remains independently installable and exposes versioned node and JSON
  contracts.
- The Unreal bridge will be a separate installable repository when creation is authorized.
- Reusable AIToolTA control-plane/runtime concepts are consumed through shared packages or
  versioned protocol contracts, not copied source trees.
- ArtFlow owns canonical run state, approval state and the authoritative generation receipt.
- Runtime nodes may contribute validation evidence but do not create a competing canonical receipt.

## Consequences

This adds protocol-version work and integration tests, but preserves independent installation,
clear ownership and credible portfolio boundaries. The suite can be demonstrated together without
claiming that one monorepo is a single deployable application.

