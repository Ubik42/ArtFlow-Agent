# Unreal 集成

- `ArtFlowSceneBridge/` 是可独立安装的 Editor 插件；
- `ArtFlowBridgeHost/` 是项目自有 UE 5.8 验证宿主，不是用户生产项目。

当前宿主保存真实 PCG 测试图和 `ArtFlowDemo` fixture。`Binaries`、`Intermediate`、`Saved`
与 `DerivedDataCache` 仍是忽略的运行产物；冻结证据复制到 `artifacts/goal/` 并由独立验证器检查。
