# M23-S2 · ComfyUI PBR、Blender 装配与 Unreal 回流

本切片把已有真实 ComfyUI Production Nodes PBR 结果继续带入 DCC 与引擎，而不是停留在贴图展示。固定 Blender 能力读取内容哈希绑定的建模源与 PBR 回执，将 Base Color、DirectX Normal 和 Roughness 装配到 `M_AF_Stone` 与 `M_AF_Weathering`，保留可编辑源并导出嵌入贴图的 GLB。Unreal Interchange 随后将精确产物对账到当前 Session 派生候选关卡。

| Blender 材质装配预览 | Unreal 候选回流 |
| --- | --- |
| ![PBR 装配后的 Blender 资产](../../artifacts/goal/m23-s2-blender-pbr/AF_WeatheredShrine_PBR-preview.png) | ![PBR 资产回流 Unreal](../../artifacts/goal/m23-s2-blender-pbr/unreal-blender-candidate.png) |

| 阶段 | 结果 |
| --- | --- |
| PBR 来源 | 已验证 ComfyUI 五通道回执；本次使用 Base Color、Normal、Roughness |
| Blender 宿主 | 5.2.0 LTS |
| 材质目标 | `M_AF_Stone`、`M_AF_Weathering` |
| 可编辑源 | `AF_WeatheredShrine_PBR.blend` |
| 引擎交换 | 嵌入贴图 GLB，5,915,996 bytes |
| Unreal 宿主 | 5.8.1-56057345 |
| Unreal StaticMesh | 2,032 顶点、952 个构建三角面、3 个材质槽、1 个简单碰撞 |
| 候选关卡 | `/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Blender_B_187f272db035` |
| 重复执行 | `reconciled`，重复副作用 0 |
| 源关卡 | SHA-256 前后均为 `620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a` |

Unreal GUI 验证只启动项目拥有的 PID 47636，启动前不存在其他 UnrealEditor 进程，执行完成后自行退出。截图 API 的结果在编辑器帧结束时异步落盘，因此回流工具先提交捕获请求，固定 finalizer 在该进程退出后验证非空图片并完成内容哈希回执；这不是用户审批步骤。

本切片证明 Blender 已经承担材质装配与引擎交换，而不只承担模型生成。尚未声称 Blender 作业已经由当前 Session 的 append-only 工作队列直接领取；该编排提升是下一切片的唯一目标。
