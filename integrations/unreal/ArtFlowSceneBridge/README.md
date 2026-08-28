# ArtFlow Scene Bridge

ArtFlow 的 Unreal Editor 插件。它从真实关卡导出原子 `scene-constraint-package/1` ZIP，当前包含：

- beauty、linear depth、world normal、object ID 四个 Render Pass；
- `scene-digital-twin/1`：Actor、变换、边界、标签、Data Layer、材质槽、灯光、PCG 与权限事实；
- `scene-change-plan/1`：仅允许灯光和已审阅 PCG 图的类型化依赖 DAG；
- `scene-dry-run-receipt/1`：暂存策略、保护对象指纹和源关卡零写入证明。

## 编辑器入口

**Tools → ArtFlow** 提供两个命令：

- **Export ArtFlow Scene Package**：捕获当前明确选择和三维场景事实；
- **Show Last ArtFlow Export**：显示最近一次完整包路径，不创建人工审批门禁。

选择合同：

1. 恰好一个 `CameraActor`；
2. 至少一个带 `ArtFlow.Protected` 标签的 Actor；
3. 至少一个带 `ArtFlow.Editable` 标签的 Actor；
4. 至少一个灯光和一个绑定 `/Game/ArtFlow/PCG/` 已审阅图的 `UPCGComponent`；
5. 项目内 `Config/ArtFlowSceneBridge.json` 美术目标。

任何 Pass、哈希、三维事实或 dry-run 合同失败时都不发布 ZIP。ZIP 先写 `.partial`，所有文件成功后
才原子移动到最终路径。

## 项目自有宿主验证入口

以下参数只用于 `ArtFlowBridgeHost`，不接受模型文本、Python、Blueprint 或任意控制台输入：

- `-ArtFlowPrepareDemo`：一次性为项目自有 `ArtFlowDemo` 加入真实 PCG Graph/Component；
- `-ArtFlowDryRunExport`：只读源关卡并导出三维事实、计划和零写入收据，随后自动退出；
- `-ArtFlowCreateDemoAndExport`：保留的旧基线入口，不作为 M7 零写入证据。

独立验证：

```powershell
.\.venv\Scripts\python scripts\verify_scene_dry_run.py `
  artifacts\goal\m7-s1-scene-dry-run\scene-package.zip `
  --source-map integrations\unreal\ArtFlowBridgeHost\Content\ArtFlowDemo.umap `
  --source-map-sha256-before <运行前哈希>
```
