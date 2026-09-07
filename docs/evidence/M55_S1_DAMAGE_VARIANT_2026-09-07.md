# M55-S1 · 场景条件破损变体

当前 Scene Session 的深度、目标区域、保护区和 M47 模块化场景身份被编译为一个有限破损任务。固定 ComfyUI 节点图生成空间损伤场，Blender 将该场转换为可编辑 Boolean 切口与材质节点，Unreal 再把交换资产写入 M47 派生的隔离候选。

## 三宿主结果

- ComfyUI 0.28.0 / RTX 4080：固定 15 节点 recipe `scene-damage-field-v1`；损伤场覆盖率 0.038307；保护区泄漏 0
- Blender 5.2 LTS：目标 `SM_AF_Module_Gateway`；7 个保留在 `.blend` 中的 Boolean 修改器；`UVMap`；1 个损伤材质；2,594 三角面 / 6,000 预算
- GLB：glTF 2.0 头与声明长度一致；186,944 bytes
- Unreal 5.8.1：导入 1 个 Static Mesh、1 个材质槽和 1 个凸碰撞体，替换登记目标并保留独立展示 Actor
- 派生候选：`/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Damage_B_fdfe74fd21b1`
- 重复回流：新增 Actor 0、更新 Actor 0、重复资产 0；M47 源候选前后 SHA-256 一致

## 恢复事实

首轮 Unreal 执行在资产与候选保存后因相机组件 API 不匹配中止。修正只影响截图适配器；后续运行先查找已写入的请求元数据和候选身份，再继续截图，没有再次导入资产或复制关卡。最终回执为 `reconciled`，完成标记只写入一次。

## 证据

- `artifacts/goal/m55-s1-damage-variant/damage-variant-request.json`
- `artifacts/goal/m55-s1-damage-variant/comfy-damage-field-receipt.json`
- `artifacts/goal/m55-s1-damage-variant/damage-field.png`
- `artifacts/goal/m55-s1-damage-variant/blender-damage-variant-receipt.json`
- `artifacts/goal/m55-s1-damage-variant/AF_GatewayDamage.blend`
- `artifacts/goal/m55-s1-damage-variant/SM_AF_Module_Gateway_Damaged.glb`
- `artifacts/goal/m55-s1-damage-variant/AF_GatewayDamage-preview.png`
- `artifacts/goal/m55-s1-damage-variant/unreal-damage-variant-receipt.json`
- `artifacts/goal/m55-s1-damage-variant/unreal-damage-variant-candidate.png`
- `scripts/verify_m55_damage_variant.py`
