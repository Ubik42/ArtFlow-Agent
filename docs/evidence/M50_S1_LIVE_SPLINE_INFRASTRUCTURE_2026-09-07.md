# M50-S1 · 当前 Session 样条基础设施路线派发

M49 的场景条件、ComfyUI 走廊、Blender 曲线编辑源和 Unreal Spline 候选已登记为当前 Scene Session 的第十七项有限生产能力。实现复用既有 `SceneDccWorkDefinition`、SQLite append-only 事件、确定性 reducer 和本地 Worker，没有建立新的状态机或宿主执行入口。

## 运行结果

- work：`dcc-work-c00a675e1d95`
- capability：17 项；新增 `blender.geometry_nodes.spline_infrastructure.v1`
- 内容绑定：M49 请求、走廊回执、Blender 回执、交换资产、布局清单与 Unreal 回执均通过哈希验证
- 拓扑验证：2 条 Spline、14 个控制点、12 个线路段、8 个支架
- 生命周期事件：5 个
- 重复派发：同一 work identity
- 终态：`succeeded`
- 重放：与终态投影一致
- 重复外部副作用：0
- 最终候选：`/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Spline_B_63cab976001a`

中文场景变更谱将“场景条件 → 路线走廊 → Blender 曲线/GN → Unreal Spline”组织成一条可检查生产路线。桌面 1600×1000 与窄屏 980×1000 均完成实际页面捕获，无横向溢出或失败媒体，浏览器控制台 0 error、0 warning。

## 证据

- `artifacts/goal/m50-s1-live-spline-infrastructure/live-spline-infrastructure-work-receipt.json`
- `artifacts/goal/m50-s1-live-spline-infrastructure/live-spline-infrastructure-desktop.png`
- `artifacts/goal/m50-s1-live-spline-infrastructure/live-spline-infrastructure-narrow.png`

