# M45-S1 · 生物群落植被与风材质回流

本切片把 M42 的 ComfyUI 生物群落蒙版和 18 个空间点编译为有限 DCC 请求。请求固定来源候选、蒙版、点集、三种植被配方、单变体三角面预算和 Unreal 消费能力；Blender 与 Unreal 只执行登记过的脚本和参数槽。

## 实际结果

- Blender 5.2.0 LTS 生成 `reed`、`fern`、`broadleaf` 三个可编辑变体；源文件保留 Geometry Nodes 配方、`UVMap`、LOD1 与显式盒碰撞代理。
- 基础网格分别为 144、120、96 个三角面；LOD1 分别为 56、44、44 个三角面，均低于基础网格的 60%。
- Unreal 5.8.1 通过 Interchange 导入三组 GLB 与 LOD，建立一个项目自有 WPO 风材质、三个有限参数实例和一个派生 PCG 图。
- PCG 从 M42 点集生成 18 个植被实例，写入候选 `/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Foliage_B_33eb6be804c2`。
- 第二次回流状态为 `reconciled`，重复外部副作用为 0；上游地形候选前后 SHA-256 保持 `3f116545...f8710`。

## 证据

- `artifacts/goal/m45-s1-foliage-kit/foliage-kit-request.json`
- `artifacts/goal/m45-s1-foliage-kit/blender-foliage-kit-receipt.json`
- `artifacts/goal/m45-s1-foliage-kit/AF_BiomeFoliage-preview.png`
- `artifacts/goal/m45-s1-foliage-kit/unreal-biome-foliage-receipt.json`
- `artifacts/goal/m45-s1-foliage-kit/unreal-biome-foliage-candidate.png`

这是从二维控制场到三维环境层的真实管线：ComfyUI 负责空间分区，Blender 负责可编辑几何、LOD、UV 与交换资产，Unreal 负责材质运行时、PCG 布置和候选关卡。它不暴露任意节点图或宿主代码执行。
