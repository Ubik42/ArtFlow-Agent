# M49-S1 · 场景约束样条基础设施

当前 Scene Session 的深度、保护区、模块区域场和 M47 候选被编译为两条有限基础设施路线。固定 ComfyUI 节点图生成可通行走廊，Blender 以 Curve 与 Geometry Nodes 保留可编辑线路，Unreal 在派生候选中重建真实 `SplineComponent`、可见线路段和支架。

## 实机结果

- 请求：`spline-infrastructure-63cab976001a87fe`
- ComfyUI：0.28.0，RTX 4080，15 节点固定子图，运行时可见 1,309 节点
- 路线走廊：覆盖率 13.3179%，保护区泄漏 0
- Blender：5.2.0 LTS；2 条 Curve / Geometry Nodes 路线、14 个控制点、8 个支架位置
- Unreal：5.8.1；2 个 `SplineComponent`、12 个可见线路段、8 个支架 Actor
- 派生候选：`/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Spline_B_63cab976001a`
- 对账重跑：`reconciled`；新增 Actor 0；重复外部副作用 0
- 上游模块候选：运行前后 SHA-256 均为 `cb9f6b486ed4b54d74ac517f88cc6ab4d72b6fd1099fe00c33f53fe1e2cd48ff`
- Unreal Map Check：0 error、0 warning

## 这条路线证明的能力

Blender 在这里不是一次性“生成模型”的黑盒，而是曲线、Geometry Nodes、可编辑场景源和交换资产的 DCC 执行面。ComfyUI 负责受约束的二维空间场，Agent 负责把它编译为有限路线和宿主合同；Unreal 继续拥有最终可编辑样条、Actor 身份和候选关卡，不接收任意 Python 或任意节点图。

## 证据

- `artifacts/goal/m49-s1-spline-infrastructure/spline-infrastructure-request.json`
- `artifacts/goal/m49-s1-spline-infrastructure/comfy-route-corridor-receipt.json`
- `artifacts/goal/m49-s1-spline-infrastructure/route-corridor.png`
- `artifacts/goal/m49-s1-spline-infrastructure/AF_SplineInfrastructure.blend`
- `artifacts/goal/m49-s1-spline-infrastructure/AF_SplineInfrastructure-preview.png`
- `artifacts/goal/m49-s1-spline-infrastructure/AF_SplineInfrastructure-manifest.json`
- `artifacts/goal/m49-s1-spline-infrastructure/SM_AF_SplineSegment.glb`
- `artifacts/goal/m49-s1-spline-infrastructure/SM_AF_SplineSupport.glb`
- `artifacts/goal/m49-s1-spline-infrastructure/blender-spline-infrastructure-receipt.json`
- `artifacts/goal/m49-s1-spline-infrastructure/unreal-spline-infrastructure-receipt.json`
- `artifacts/goal/m49-s1-spline-infrastructure/unreal-spline-infrastructure-candidate.png`

