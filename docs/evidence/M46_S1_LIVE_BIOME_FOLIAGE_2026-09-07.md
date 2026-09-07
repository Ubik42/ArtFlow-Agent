# M46-S1 · 当前 Session 植被路线派发

M45 的生物群落、Blender 编辑源和 Unreal 环境候选已登记为当前 Scene Session 的第十五项有限生产能力。实现沿用既有 `SceneDccWorkDefinition`、SQLite append-only 事件、确定性 reducer 和本地 Worker，没有建立新的状态机。

## 运行结果

- work：`dcc-work-3ce568e90543`
- capability：15 项；新增 `blender.geometry_nodes.biome_foliage_kit.v1`
- 生命周期事件：5 个
- 重复派发：同一 work identity
- 终态：`succeeded`
- 重放：与终态投影一致
- 重复外部副作用：0
- 最终候选：`/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Foliage_B_33eb6be804c2`

中文场景变更谱展示 ComfyUI 群落场、Blender 三物种编辑源和 Unreal PCG/WPO 结果。桌面 1600×1000 与窄屏 980×1000 均完成实际页面捕获，浏览器控制台 0 error、0 warning。

## 证据

- `artifacts/goal/m46-s1-live-foliage/live-biome-foliage-work-receipt.json`
- `artifacts/goal/m46-s1-live-foliage/live-biome-foliage-desktop.png`
- `artifacts/goal/m46-s1-live-foliage/live-biome-foliage-narrow.png`
