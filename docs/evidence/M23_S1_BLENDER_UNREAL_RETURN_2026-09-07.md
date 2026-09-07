# M23-S1 · Blender 自主生成与 Unreal 回流

当前 Scene Session 的源关卡身份、尺度和资产意图被编译为 `artflow-blender-modeling-request/1`。Blender 5.2 LTS 通过注册能力 `blender.architectural_prop.weathered_shrine.v1` 生成模块化祭坛的可编辑源、单体 GLB 和预览图；Unreal 5.8.1 使用 Interchange 将相同 GLB 导入内容寻址目录，并放入 Session 派生候选关卡。

| Blender 生成预览 | Unreal 候选关卡 |
| --- | --- |
| ![Blender 模块化建筑道具](../../artifacts/goal/m23-s1-blender-modeling/AF_WeatheredShrine-preview.png) | ![Unreal 中的 Blender 生成资产](../../artifacts/goal/m23-s1-blender-modeling/unreal-blender-candidate.png) |

| 阶段 | 结果 |
| --- | --- |
| Blender 宿主 | 5.2.0 LTS |
| Blender 编辑源 | 26 个 Mesh 构件、3 个材质、2,496 顶点、4,888 三角面 |
| 引擎交换 | 单体嵌入式 GLB，352,040 bytes |
| Unreal 宿主 | 5.8.1-56057345 |
| Unreal StaticMesh | 2,032 顶点、952 个构建三角面、3 个材质槽、1 个简单碰撞 |
| 候选关卡 | `/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Blender_B_b717f8d475db` |
| 重复执行 | `reconciled`，重复副作用 0 |
| 源关卡 | SHA-256 前后均为 `620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a` |

真实 GUI 验证进程 PID 为 38876，完成同一请求对账后自行退出；启动前没有其他 UnrealEditor 进程。本切片只验证一个类型化合同、一次 Blender 生成和一次 Unreal 回流。

当前能力是 Agent 驱动的参数化 DCC 生成，并未声称使用训练式 Text-to-3D 模型。下一切片将把该工作纳入当前 Session 队列，并把现有 ComfyUI PBR 子图生成的贴图装配到 Blender 资产后再回流 Unreal。
