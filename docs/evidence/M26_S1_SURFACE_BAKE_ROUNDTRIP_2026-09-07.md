# M26-S1 · Blender Surface Bake 与 Unreal 回流

当前 Lookdev 方向已经从二维目标和灯光材质预演继续落实为可复用的引擎表面资产。

| Blender 5.2 可编辑 Bake 结果 | 1024² Base Color 图集 | Unreal 5.8 隔离候选 |
| --- | --- | --- |
| ![带单一 Bake 材质的庭院资产](../../artifacts/goal/m26-s1-surface-bake/AF_ShrineCourtyard_Baked-preview.png) | ![ArtFlow_BakedUV 对应的 Base Color](../../artifacts/goal/m26-s1-surface-bake/AF_ShrineCourtyard_Baked_BaseColor.png) | ![Interchange 回流后的表面候选](../../artifacts/goal/m26-s1-surface-bake/unreal-surface-candidate.png) |

## 实际执行

- Surface Request 绑定 `scene-session-dc31f6ed0f4e`、M24 Lookdev 请求与回执、源 `.blend` 哈希，以及 27 个登记对象；调用方不能提交 Blender Python、任意对象路径或材质图。
- Blender 5.2.0 LTS 将参数化对象与 Geometry Nodes 计算结果合并为一个可编辑表面资产，生成名为 `ArtFlow_BakedUV` 的 UV 集。
- UV 展开包含 11,104 个 loop，图集面积占比为 `0.228371`；生成 1024×1024 Base Color 与 Roughness PNG、单材质 GLB、`.blend` 和 1280×720 预览。
- Blender 输出为 2,818 顶点 / 5,364 三角形；固定验证器检查请求身份、五个制品哈希、纹理尺寸、UV 非空、单一材质槽和几何预算。
- Unreal 5.8.1 Interchange 导入一个 StaticMesh、一个材质和两张纹理，建立 `Surface_B_9cbf7f1f20ab` 隔离候选；第二次运行返回 `reconciled`。

## 结果边界

- `ArtFlowDemo.umap` 执行前后 SHA-256 均为 `620e4814…d24974a`。
- 重复外部副作用为 0，候选、网格、材质和纹理按 Surface Request 哈希对账。
- 本切片复用已经接受的 ComfyUI 场景条件目标，没有重新生成图片，也没有新增审批或并行状态机。
- 冻结请求、Blender/Unreal 回执、真实宿主日志、贴图、交换资产和截图位于 `artifacts/goal/m26-s1-surface-bake/`。
