# M3-S10 — Real Unreal Scene Package Bridge

Date: 2026-08-25

## Result

ArtFlow now owns a separately installable, editor-only Unreal plugin and a disposable host project.
The plugin exported one real camera-bound Scene Package from Unreal Engine 5.8.1. The existing
Python archive boundary and the compiled C++ contract verifier independently accepted that exact
archive, while a modified pass was rejected before an Agent run could be created.

This slice also removes the earlier invented authorization gate around project-owned Unreal
development. Editing and testing the Bridge and its disposable host are ordinary repository work.
Unrelated projects and shared engine installations remain outside scope.

## Real package identity

- Package: `artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6`
- Archive SHA-256: `130c94284deb5fddb18c52d604b615ca1a071e42afc8149604f76130fe412f76`
- Source: Unreal Engine `5.8.1-56057345+++UE5+Release-5.8`, project `ArtFlowBridgeHost`, map `/Game/ArtFlowDemo`
- Camera: perspective, 55-degree field of view, 640 × 360 output
- Protected region: `Protected_Blockout`
- Editable region: `Editable_Form`

| Pass | Format | SHA-256 |
| --- | --- | --- |
| beauty | PNG | `f6d4005d…` |
| depth | EXR | `348e4e37…` |
| world normal | EXR | `15de4b75…` |
| object ID | PNG | `991868d3…` |

The complete digests remain in the package manifest rather than being duplicated into narrative
documentation.

## Bridge behavior

- `Tools → ArtFlow → Export ArtFlow Scene Package` requires exactly one selected camera, at least
  one `ArtFlow.Protected` actor and at least one `ArtFlow.Editable` actor.
- Beauty, linear depth, world normal and object ID are captured from the same scene/camera contract.
- Each artifact is hashed, written under a staging directory and then published as one atomic ZIP.
- Cancellation, missing selections, output path escape and incomplete capture fail closed.
- Startup removes stale staging and `.partial` files left by interrupted work.
- The model is never given arbitrary Python, Blueprint, console or ComfyUI graph execution.
- `Review Last ArtFlow Export` displays the immutable export path; it does not silently adopt or
  mutate an Unreal asset.

## Verification

- UnrealBuildTool compiled the plugin and disposable host against UE 5.8.
- A visible editor run created `/Game/ArtFlowDemo`, exported the package and displayed the review
  dialog. Human-visible evidence: `artifacts/goal/m3-s10-visible-unreal-host.png`.
- The exact archive is preserved at
  `artifacts/goal/m3-s10-real-unreal-scene-package.zip`.
- The cross-language fixture under `artifacts/goal/m3-s10-cross-language/` passed the Unreal-side
  C++ verifier and Python `ScenePackageArchive` verifier.
- Changing `passes/depth.exr` caused Python verification to fail with a scene artifact hash
  mismatch.
- Scene Lab imported the ZIP through its real upload control, served the exact verified passes and
  labeled the source `REAL UNREAL CAPTURE` / `READ-ONLY IMPORT`.
- Browser evidence at 1440 px and 390 px has no horizontal overflow, both PNGs decode, and the
  browser console reports zero errors:
  - `artifacts/goal/m3-s10-scene-lab-real-unreal-wide.png`
  - `artifacts/goal/m3-s10-scene-lab-real-unreal-narrow.png`

## Failure discovered and corrected

The first visible run reached Unreal's Windows SHA-256 platform stub, which asserts at runtime in
UE 5.8. No archive was published. The Bridge now uses its own deterministic SHA-256 implementation
with a known-empty-digest self-check. A subsequent run exported successfully. A later restart also
proved stale staging and partial-package cleanup, with zero remaining staged files.

## Evidence ceiling

This proves real Unreal capture, package integrity, cross-language verification and read-only Agent
ingress. It does **not** prove image generation, provider comparison, tribunal evaluation, human
adoption, revision or Unreal reimport. The scene is deliberately small and is not presented as a
production rendering benchmark.
