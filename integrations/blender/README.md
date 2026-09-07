# Blender DCC Bridge

该目录保存 ArtFlow 注册的 Blender 生产能力。当前 `blender.architectural_prop.weathered_shrine.v1` 接收类型化尺寸、层级、立柱数、细节、随机种子和材质色板，由 Blender 5.2 LTS 生成：

- 保留分件和材质的可编辑 `.blend`；
- 合并为单体引擎资产的嵌入式 GLB；
- 用于候选选择和文档展示的 Blender 预览图；
- 记录真实对象、顶点、三角面、边界和产物哈希的结构化回执。

Agent 选择能力并填写规格，不提交 Blender Python。`generate_architectural_prop.py` 是随项目版本化的固定执行器。后续能力会在同一接口下增加 Geometry Nodes、ComfyUI PBR 装配与 Bake、场景布局、相机灯光交换和 Alembic 模拟缓存。

开发复现：

```powershell
uv run python scripts/run_m23_blender_candidate.py
```

生成结果位于 `artifacts/goal/m23-s1-blender-modeling/`。Unreal 回流由 `integrations/unreal/import_blender_scene_candidate.py` 完成，目标始终位于 ArtFlow 的 Session 派生候选目录。
