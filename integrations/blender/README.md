# Blender DCC Bridge

该目录保存 ArtFlow 注册的 Blender 生产能力。当前 `blender.architectural_prop.weathered_shrine.v1` 接收类型化尺寸、层级、立柱数、细节、随机种子和材质色板，由 Blender 5.2 LTS 生成：

- 保留分件和材质的可编辑 `.blend`；
- 合并为单体引擎资产的嵌入式 GLB；
- 用于候选选择和文档展示的 Blender 预览图；
- 记录真实对象、顶点、三角面、边界和产物哈希的结构化回执。

Agent 选择能力并填写规格，不提交 Blender Python。`generate_architectural_prop.py` 是随项目版本化的固定建模执行器；`assemble_comfy_pbr.py` 读取内容哈希绑定的建模回执和已验证 ComfyUI PBR 回执，把 Base Color、DirectX Normal 与 Roughness 装配到声明的 Blender 材质槽。`generate_geometry_layout.py` 再根据 Session 边界、数量、变化幅度和种子建立固定 Geometry Nodes 图，保留可编辑实例布局，并为 Unreal 实现为单一交换资产。`apply_camera_light_shot.py` 读取 Unreal 登记的相机与灯光事实，在相同镜头下生成有界三点灯光方案和可编辑场景，不接收任意宿主代码或属性路径。

开发复现：

```powershell
uv run python scripts/run_m23_blender_candidate.py
uv run python scripts/run_m23_blender_pbr.py
uv run python scripts/run_m23_geometry_layout.py
uv run python scripts/run_m23_blender_shot.py
```

建模和材质装配结果分别位于 `artifacts/goal/m23-s1-blender-modeling/` 与 `artifacts/goal/m23-s2-blender-pbr/`。Unreal 回流由 `integrations/unreal/import_blender_scene_candidate.py` 完成，目标始终位于 ArtFlow 的 Session 派生候选目录。高分辨率截图由编辑器异步落盘，固定 finalizer 在所拥有的 Unreal 进程退出后完成截图哈希与回执，不需要人工确认。

四条能力已经复用同一 DCC 工作生命周期：模块化建模、ComfyUI PBR 装配、Geometry Nodes 场景布局，以及 Unreal ↔ Blender 相机灯光交换。后续 Alembic 模拟缓存仍沿用这套契约，而不是为每类 Blender 功能另建状态系统。
