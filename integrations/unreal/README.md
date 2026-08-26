# Unreal integration

- `ArtFlowSceneBridge/` is the separately installable editor plugin.
- `ArtFlowBridgeHost/` is the ArtFlow-owned disposable UE 5.8 validation project.

The host is evidence infrastructure, not a sibling product and not a production game project. Build
and capture artifacts remain ignored runtime output under its `Binaries`, `Intermediate`, `Saved`,
`DerivedDataCache` and `Content/ArtFlowDemo.umap` paths.
