# ArtFlow Agent 2026 产品愿景

状态：稳定底座已完成，进入实时 Scene Session 产品化

决策日期：2026-08-27

能力口径：M0–M10 的持久协调、真实 Unreal 场景差量、ComfyUI PBR、四域执行、失败域纠正、MCP
边界和实验图生 3D 已有冻结证据。M11 之后的实时 Scene Session、编辑器入口和多案例产品化仍在开发。

## 一句话定位

**ArtFlow 是 Unreal 原生的“二维视觉意图到可验证三维场景变更”Agent。**

二维概念图不是最终交付物，而是目标状态和评价参照。ArtFlow 读取 Unreal 的相机、物体、材质、
灯光、PCG、空间边界和保护规则，编译一份类型化 `SceneChangePlan`，协调受控的图像、材质、
三维资产、PCG 与灯光工具，在隔离的候选场景中执行、同机位回渲、评价、纠正，最后只发布
通过技术约束和视觉评价的场景增量。

## 产品闭环

```text
Unreal 源场景
  -> Scene Digital Twin（相机 / Actor / 材质 / 灯光 / PCG / Data Layer / 多 Pass）
  -> 视觉目标（已有概念图 / 本地 ComfyUI / 开发期 Codex 内置图像生成）
  -> Scene Delta Planner（只产出类型化计划，不产出宿主代码）
  -> 依赖图与能力路由
       -> 材质与 PBR 贴图候选
       -> 现有资产检索或图生 3D 候选
       -> PCG 参数与布局候选
       -> 灯光与后处理候选
  -> Unreal Staging Executor（独立 Data Layer / Level Instance，事务化执行）
  -> 同机位回渲 + 技术检查 + 独立视觉评价
  -> 只纠正失败域
  -> 发布可回滚 Scene Delta + 资产来源与执行证据
```

## 核心创新

### 1. 从“生成图片”升级为“编译场景差量”

Agent 不把提示词或 ComfyUI 图当成权威状态。权威中间表示是 `SceneChangePlan`，其中每个操作
都声明目标对象、前置条件、读写域、依赖、预算、幂等键、验证方法和回滚信息。首批操作限定为：

- `SetLightingRig`：调整允许修改的灯光、天空与后处理参数；
- `ApplyPCGLayout`：选择已审阅 PCG 图并设置暴露参数、种子和作用边界；
- `CreateMaterialInstance`：从已审阅母材质与验证过的 PBR 贴图创建实例；
- `ImportMeshCandidate`：经 Interchange 导入隔离命名空间，检查比例、面数、材质与碰撞后才能布置；
- `PlaceOrReplaceAsset`：只作用于允许修改的 Actor 或生成层，不覆盖受保护对象。

自由文本永远不能直接变成 Blueprint、Python、Shell 或任意 ComfyUI 工作流。

### 2. Unreal 是事实源与执行宿主

Scene Digital Twin 不只是 beauty/depth/normal/object ID 图片，还应包含稳定 Actor 身份、边界盒、
标签、材质槽、光源参数、PCG 组件与图参数、Data Layer 归属、受保护关系和性能预算。所有写入
先进入 `ArtFlow_<run_id>` 暂存层；源关卡不被原地覆盖。候选可隐藏、丢弃、重放或发布。

### 3. 视觉评价与三维技术评价并列

同机位回渲负责回答“是否接近概念图”，确定性技术检查负责回答“是否仍是可用场景”。技术失败
包括保护对象变化、越界布置、碰撞、无效材质、错误比例、资源缺失或超预算。视觉评价不能覆盖
技术失败，资产生成器也不能评价并采用自己的结果。

### 4. 持久协调器，而不是表演式多 Agent 群聊

ArtFlow 保留一个可重放的协调器和多个受限角色：Scene Analyst、Visual Director、Scene Delta
Planner、Material/Asset/PCG/Lighting Specialist、Unreal Executor、Visual Critic、Technical Judge
与 Recovery Reconciler。角色用于上下文隔离和权限分离；它们通过事件和类型化产物协作，
不通过自由聊天共享隐式状态。

独立的材质、资产和灯光任务可并行准备，但 Unreal 写入只有一条事务化执行通道。失败后只重做
受影响分支，不能默认重跑全部生成。

## MCP 与工具边界

内部 Python/C++ 合同、事件状态机和策略层是唯一权威实现。ArtFlow MCP Server 是一个很薄的
互操作适配器，让 Codex 或其他兼容宿主能够检查资源并调用同一组窄工具；MCP 不拥有内部状态机，
也不暴露任意宿主执行。

建议的首批资源与工具：

| 类别 | 接口 | 权限 |
| --- | --- | --- |
| 资源 | `artflow://runs/{id}`、`artflow://scenes/{id}`、`artflow://capabilities` | 只读、内容寻址 |
| Unreal 观察 | `ue.scene.inspect`、`ue.scene.capture_package` | 只读 |
| Unreal 暂存 | `ue.stage.create`、`ue.stage.render`、`ue.stage.validate` | 项目内隔离写入 |
| Unreal 变更 | `ue.material.create_instance`、`ue.pcg.apply_plan`、`ue.light.apply_rig` | 类型化、白名单 |
| Unreal 交付 | `ue.stage.publish`、`ue.stage.discard` | 有收据、可追踪 |
| ComfyUI | `comfy.capabilities.inspect`、`comfy.workflow.compile`、`comfy.workflow.execute` | 已审阅子图与插槽 |
| 生成资产 | `asset.pbr.generate`、`asset.mesh.generate` | 可替换 Provider，先产候选 |
| 评价 | `eval.visual.compare`、`eval.scene.validate` | 只读，不能发布 |

ComfyUI 的“画布式能力”实现为**经过审阅的子图目录 + 类型化图编译器**：Agent 可以根据能力清单
组合允许的子图并填充插槽，但不能随意拖节点、安装自定义节点或执行模型生成的任意图。现有
`ComfyUI-Production-Nodes` sibling 仓库需要通过版本化能力清单和真实 `/object_info` 探测接入；
在完成该验证前，不能声称它已被 ArtFlow 使用。

## Provider 策略

- Codex 内置图像生成是当前开发编排器可用的能力，用于制作目标图、解释图和受控修订；它不是
  ArtFlow 可独立部署运行时中的远程 API，公开架构必须明确这一点。
- 本地 ComfyUI 是可部署图像/PBR/控制图执行面；后续通过固定子图而不是 UI 自动化接入。
- TRELLIS.2、Hunyuan3D 等图生 3D 能力只作为 `asset.mesh.generate` 的可替换实验适配器。
  首个闭环必须能只用项目自有资产和 PCG 完成，避免硬件、许可证或模型质量阻塞主线。
- 优先复用项目资产；生成新网格必须经过 Interchange、几何与性能验证，不能直接替换生产对象。

## 真实演示场景

第一条三维演示选择“废墟祭坛视觉开发”：用户提供一张目标概念图，Agent 保持相机、主体祭坛和
可行走区不变，在候选层中完成冷暖灯光重构、雾与后处理调整，并通过固定 PCG 图布置项目自有的
碎石、发光柱和地表点缀。系统用同机位前后对照、保护对象哈希、PCG 种子、Actor 数量、越界与
碰撞检查证明变更真实发生在三维场景中。

后续演示再增加：

1. 从概念图生成或重绘一组 PBR 材质，创建材质实例并替换指定表面；
2. 从单体参考图生成 GLB 候选，经验证后加入 PCG 资产集合，而不是直接替换核心场景；
3. 在同一视觉目标下比较“只用现有资产”和“允许生成资产”两条路线的成本、耗时和质量。

演示素材优先使用项目自有 UE 基础体和确定性生成的小型道具；若引入公开素材，必须在 manifest
中记录来源、许可证、哈希和用途。每个里程碑保留多张真实流程截图，不用界面 mock 代替宿主证据。

## 非目标

- 通用 3D 世界生成器或一句话生成完整游戏；
- 让模型任意修改源关卡、蓝图、C++、Python 或 ComfyUI 图；
- 用 MCP 替代 Agent runtime，或为“技术新”无条件引入 LangGraph、Temporal、向量库；
- 第一阶段训练自己的基础模型或押注单一图生 3D 模型；
- 把二维预览平面回流描述成真实二维到三维转换；
- 用离线模拟器数据冒充真实远程 Provider 故障恢复证据。

## 成功标准

作品集最终应让评审者看到：ArtFlow 能理解真实 Unreal 场景，依据二维目标规划多个相互依赖的
三维变更，通过窄工具和持久事件自主执行，在隔离层中回渲、评价、局部纠错，并以可回滚、可验证、
带来源的场景增量交付。复杂度来自真实的上下文、权限、调度、恢复与验证问题，而不是框架数量。
