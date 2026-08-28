# ArtFlow 三维场景变换演示计划

状态：M7–M10 演示合同

场景：项目自有 `ArtFlowBridgeHost /Game/ArtFlowDemo`

主题：废墟祭坛视觉开发

## 给评审者看的故事

一个关卡美术师已经完成祭坛灰盒、主相机和可行走区域，希望根据一张氛围概念图快速得到可继续
编辑的三维候选。ArtFlow 不把概念图贴回场景充数，而是读取关卡事实，保留相机、祭坛和通道，
规划灯光、雾、材质与 PCG 道具布置，在隔离候选层中执行，同机位回渲并检查越界、碰撞和预算。
如果碎石堵住通道，只重做 PCG 分支；如果灯光偏离目标，只重做灯光分支。通过的候选可以发布，
不满意的候选可以完整丢弃。

## 项目自有测试素材

首个闭环不下载第三方美术资产，使用 UE 基础几何和项目脚本确定性合成，避免许可证与网络影响：

| 素材 | 生成方式 | 状态 | 用途 |
| --- | --- | --- | --- |
| 祭坛主体 | 现有 `ArtFlowDemo` 基础体组合 | 已存在 | 受保护结构与视觉主体 |
| 地面和通道 | 现有基础网格 | 已存在 | PCG 禁入区与碰撞验证 |
| 程序化石锥道具 | UE Cone 复制为项目内资产、固定 12 点布局 | M7-S2 已验证 | PCG scatter 与幂等对账 |
| 发光柱两件套 | cylinder/cube + 项目自有母材质实例 | M9 计划 | PCG 重点物与灯光响应 |
| 地表点缀 | plane/cube 组合 | M9 计划 | 密度、坡度和边界演示 |
| 目标概念图 | Codex 内置图像生成或项目自有合成图 | M9 生成 | 视觉意图，不作为三维事实 |
| PBR 材质组 | 固定 ComfyUI 子图生成 | M8 生成 | BaseColor/Normal/Roughness 等验证 |
| 图生 3D 单体 | 可选 TRELLIS.2/其他 Provider | M10 实验 | Interchange 接纳/拒绝对照 |

每个生成素材在 `demo/asset-manifest.json`（实现阶段创建）记录 `asset_id`、生成器、输入哈希、种子、
许可证、输出哈希、Unreal 路径和当前验证状态。若后续使用 Poly Haven 等公开 CC0 素材，也必须把
原始下载页和许可证快照加入 manifest，不能只写“免费素材”。

## 演示变更合同

源场景固定不变量：

- `ArtFlow_Camera` 的投影、变换与画幅；
- 祭坛主体 Actor 身份、变换、边界和静态网格；
- 可行走通道和 PCG 禁入体积；
- 源关卡包和受保护资产哈希。

Agent 可修改域：

- 专用候选层中的 Directional Light、Sky Light、Exponential Height Fog 和 Post Process 参数；
- 已审阅 PCG 图暴露的 seed、density、scale range、asset set、exclusion volume 与 color tag；
- `/Game/ArtFlow/Generated/<run_id>` 下的项目生成资产与 Material Instance；
- 候选层中新建的 Actor，不得无指纹替换源 Actor。

第一条计划 DAG：

```text
inspect_scene
  -> create_stage
  -> apply_lighting -----------------------> render_candidate
  -> prepare_project_owned_prop_set
       -> apply_pcg_layout ----------------> render_candidate
render_candidate
  -> technical_validate
  -> visual_compare
  -> correct_failed_domain (0..1)
  -> publish_or_discard
```

## 真实验证指标

- 受保护 Actor 指纹变化数：必须为 0；
- 源关卡提交写入数：暂存期必须为 0；
- PCG seed 和图版本：必须可重放；
- 禁入区实例数、阻塞通道实例数：必须为 0；
- 新增 Actor、三角面、材质槽、纹理显存：必须低于演示预算；
- 技术失败后的重复成功分支执行数：必须为 0；
- 回渲视觉分数只作为方向信号，不能覆盖上述确定性失败。

## 截图与录屏矩阵

所有截图来自同一真实 run，中文说明不得覆盖关键宿主事实：

1. Unreal 源关卡、相机与受保护主体；
2. Scene Digital Twin 的 Actor / Light / PCG 事实页；
3. 目标概念图与 Visual Director 拆解；
4. SceneChangePlan 依赖图、写入域和预算；
5. Unreal 暂存层/Data Layer 创建结果；
6. PCG 图、暴露参数与确定性 seed；
7. 灯光分支真实执行前后；
8. PCG 布局真实执行前后；
9. 同机位源图、目标图和候选回渲三联对照；
10. 技术 Judge 的保护对象、越界、碰撞与预算结果；
11. 一个失败域被局部纠正、其他分支未重跑；
12. Unreal 最终候选层与发布/丢弃 receipt；
13. ComfyUI PBR 子图与真实输出收据（M8）；
14. 图生 3D GLB 的 Interchange 接纳或拒绝证据（M10）；
15. MCP 外部调用与同一 ArtFlow 事件 ID（M10）。

最终 README 首屏只选最能证明“二维意图确实改变了三维场景”的 6–8 张，其余进入案例研究。
