# M51-S1 · 程序化机关绑定与动画回流

当前 Scene Session 的视觉目标和 M49 样条候选被编译为有限双扇机关任务。Blender 生成可编辑网格、Armature、刚性权重与开合 Action；Unreal 将同一 FBX 导入为 Skeletal Mesh、Skeleton 和 AnimSequence，并放入新的隔离候选关卡。

## 实机结果

- 请求：`mechanism-rig-5122fe6e5daf6ab1`，SHA-256 `2762b53baeecceb5c5067842741dde60900eda311a5723c4752fab2213481b2c`
- Blender：5.2.0 LTS；3 个登记变形骨骼、2 个关节、6 个关键姿态，帧段 1–48 / 24 fps
- 几何：1,120 顶点、2,160 三角形、3 个材质槽、命名 UVMap
- 交换：可编辑 `.blend`、带蒙皮和动画的 FBX、结构清单、开门姿态预览
- Unreal：5.8.1；真实导入 Skeletal Mesh、Skeleton、AnimSequence，并创建唯一机关 Actor
- FBX 适配：Unreal 检测到 Blender Armature 传输根；其下 `root → hinge_left / hinge_right` 变形层级与清单一致。Bounds 显示 FBX 单位为米，返回工具以记录的 `99.999994` 比例适配为厘米
- 派生候选：`/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Mechanism_B_2762b53baeec`
- 对账重跑：`reconciled`；新增 Actor 0；重复外部副作用 0
- 上游样条候选运行前后 SHA-256 均为 `c0c8880595618cb14fa99bb17ce39b882201aab523e6dfc8ad89c04cb2e9e984`

## 能力边界

模型只选择登记的 `articulated_gate_v1` 能力并填写尺寸、两关节角度、帧段和预算，不生成 Blender 或 Unreal 代码。固定 Blender 工具拥有绑定与动作制作权限；固定 Unreal 返回工具只接受内容寻址制品、隔离候选路径和登记骨骼层级。该链路覆盖 Blender 的绑定、动画和 FBX 交换能力，而非把 Blender 简化为静态建模器。

## 证据

- `artifacts/goal/m51-s1-mechanism-rig/mechanism-rig-request.json`
- `artifacts/goal/m51-s1-mechanism-rig/AF_ArticulatedGate.blend`
- `artifacts/goal/m51-s1-mechanism-rig/SK_AF_ArticulatedGate.fbx`
- `artifacts/goal/m51-s1-mechanism-rig/AF_ArticulatedGate-manifest.json`
- `artifacts/goal/m51-s1-mechanism-rig/AF_ArticulatedGate-open-preview.png`
- `artifacts/goal/m51-s1-mechanism-rig/blender-mechanism-rig-receipt.json`
- `artifacts/goal/m51-s1-mechanism-rig/unreal-mechanism-rig-receipt.json`
- `artifacts/goal/m51-s1-mechanism-rig/unreal-mechanism-rig-candidate.png`
