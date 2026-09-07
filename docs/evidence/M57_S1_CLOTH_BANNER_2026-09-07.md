# M57-S1 · 场景条件布料旗帜

当前 Unreal 候选的挂点、尺度、风向和视觉目标被编译为一个内容寻址的有限任务。固定 ComfyUI 图生成纹章与旧化输入；Blender 将它装配到可编辑材质节点和 UV，并在登记风场中求解布料；定格网格再通过 Interchange 进入从原场景派生的 Unreal 候选。

## 三宿主结果

- 请求 SHA-256：`4db41b8ff0c213f925a077d36d43294c6cdd129e9f46ddd094c0f50aa5196cf2`
- ComfyUI 0.28.0 / RTX 4080：固定 `scene-banner-pattern-v1` 节点图；纹理 `T_AF_BannerPattern.png`；回执 `8b530b6ed341af7ba5decbc5a0ed2df14d728ba7f798f86b124ce8d80e0fb001`
- Blender 5.2 LTS：可编辑对象 `SM_AF_ClothBanner_Editable`；Pin Group `AF_PinTop` 含 26 个顶点；保留 `ArtFlow Cloth`、`AF_SceneWind`、`ArtFlow_BannerUV` 和 `M_AF_SceneBanner` 节点材质
- 布料定格：第 48 帧；GLB 423,588 bytes；3,948 三角面 / 5,000 预算
- Unreal 5.8.1：1 个 Static Mesh、1 个材质槽、1 个凸碰撞体；候选 `/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/ClothBanner_B_4db41b8ff0c2`
- 第二次 Unreal 执行：`reconciled`；新增 Actor 0、更新 Actor 0、重复资产 0；源破损候选前后 SHA-256 一致

## 能力边界

这条路线验证 Blender 作为完整 DCC 执行面参与材质装配、UV、布料物理、风场和引擎交换，而不只是生成几何。模型只能选择登记能力和有限参数；ComfyUI 图拓扑与 Blender 宿主程序均为版本化实现，不向模型开放任意节点图或 Python。

## 证据

- `artifacts/goal/m57-s1-cloth-banner/cloth-banner-request.json`
- `artifacts/goal/m57-s1-cloth-banner/comfy-banner-texture-receipt.json`
- `artifacts/goal/m57-s1-cloth-banner/T_AF_BannerPattern.png`
- `artifacts/goal/m57-s1-cloth-banner/blender-cloth-banner-receipt.json`
- `artifacts/goal/m57-s1-cloth-banner/AF_ClothBanner.blend`
- `artifacts/goal/m57-s1-cloth-banner/SM_AF_ClothBanner.glb`
- `artifacts/goal/m57-s1-cloth-banner/AF_ClothBanner-preview.png`
- `artifacts/goal/m57-s1-cloth-banner/unreal-cloth-banner-receipt.json`
- `artifacts/goal/m57-s1-cloth-banner/unreal-cloth-banner-candidate.png`
- `scripts/run_m57_cloth_banner.py`
- `scripts/run_m57_cloth_banner_unreal.ps1`
