# M24-S2 · Scene-conditioned lookdev handoff

本切片验证了 ComfyUI 场景条件结果可以继续驱动真实 DCC 与引擎场景，而不是止于一张候选图。

| ComfyUI 视觉目标 | Blender 5.2 Lookdev | Unreal 5.8 隔离候选 |
| --- | --- | --- |
| ![暖色场景条件候选](../../artifacts/goal/m24-s1-scene-conditioning/depth-guided-candidate.png) | ![可编辑材质与三灯预演](../../artifacts/goal/m24-s2-scene-lookdev/AF_ShrineCourtyard_Lookdev-preview.png) | ![候选专属材质与灯光回流](../../artifacts/goal/m24-s2-scene-lookdev/unreal-lookdev-candidate.png) |

## 实际执行

- Lookdev Request 同时绑定当前 Scene Session、源关卡、M24-S1 conditioning 请求/回执、已接受图像、M23-S5 Shot Request 与源 `.blend` 的内容身份。
- 固定编译器从目标图生成三组有限 sRGB 色板：`M_AF_Stone`、`M_AF_Weathering`、`M_AF_Inlay`；宿主只接受这三个材质目标。
- 灯光只允许 `key / fill / rim` 三个登记角色。本次为暖主光 `4300K / 4.4`、冷补光 `9200K / 0.48` 与轮廓光 `6800K / 1.65`。
- Blender 5.2.0 LTS 从内容绑定的 Shot `.blend` 生成新的可编辑 `.blend` 与 1280×720 预演，耗时 1.361 秒。
- Unreal 5.8.1 从已存在的 Shot 候选派生 `Lookdev_B_4a01b62f9d58`，创建候选专属材质并覆盖生成 Actor 的三个材质槽；第二次运行返回 `reconciled`。

## 边界与结果

- 不让模型生成 Blender Python、Unreal 属性或任意 ComfyUI graph；图像只进入有限色板与登记灯光槽位。
- `ArtFlowDemo.umap` 执行前后 SHA-256 均为 `620e4814…d24974a`。
- 重复外部副作用为 0；候选、材质与 Actor 均按请求哈希对账。
- 当前实机仍没有 ControlNet / LoRA 权重，因此本切片没有虚构相应能力；上游沿用已经实测的 FLUX.2 `ReferenceLatent` 场景条件路线。

冻结请求、Blender 回执、Unreal 回执、截图与聚焦验证位于 `artifacts/goal/m24-s2-scene-lookdev/`。
