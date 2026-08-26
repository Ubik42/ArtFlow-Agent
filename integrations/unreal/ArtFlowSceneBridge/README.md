# ArtFlow Scene Bridge

Editor-only, separately installable Unreal plugin for exporting an atomic `scene-constraint-package/1`
archive. It provides two reviewed commands under **Tools → ArtFlow**:

- **Export ArtFlow Scene Package** captures the current explicit selection.
- **Show Last ArtFlow Export** displays the last completed archive path. It is informational and
  never creates an approval interrupt.

Selection contract:

1. exactly one selected `CameraActor`;
2. at least one selected actor tagged `ArtFlow.Protected`;
3. at least one selected actor tagged `ArtFlow.Editable`;
4. a human-authored `Config/ArtFlowSceneBridge.json` request.

The bridge captures beauty PNG, linear-depth EXR, world-normal EXR and custom-stencil object-ID PNG
into project-local staging. Every pass is SHA-256 hashed, the manifest is written last, and the ZIP
is published from a `.partial` file only after all evidence succeeds. Cancellation or any missing
capability deletes staging and publishes nothing.

The `-ArtFlowCreateDemoAndExport` switch exists only for the ArtFlow-owned host fixture. It creates a
fixed validation scene, selects its reviewed camera/regions, saves the map and invokes the same export
path. It does not execute Python, Blueprint, model text or arbitrary console input.
