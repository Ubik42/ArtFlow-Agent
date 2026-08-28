# ArtFlow Agent 持续开发目标

## 当前总目标

将 ArtFlow 持续开发为 **Unreal 原生的二维视觉意图到三维场景变更 Agent**。二维生成图只是
目标和证据，最终产物是 Unreal 中经过暂存、回渲、评价、纠正和验证的 `Scene Delta`。

已完成的 M0–M6（场景四 Pass、持久 Harness、Provider 路由、独立评价、恢复、记忆、来源和
作品集交付）作为可信底座保留，不重复重构。M7 起集中补齐三维事实、三维计划和三维执行。

## 稳定完成定义

1. Scene Package 扩展为 Scene Digital Twin，包含相机、多 Pass、Actor、边界、材质、灯光、
   PCG、Data Layer、保护关系和预算；
2. 模型只产出版本化 `SceneChangePlan`，不能产出或执行任意 Blueprint、Python、Shell、C++ 或
   ComfyUI 图；
3. 至少支持灯光/后处理、PCG 布局、材质实例和三维资产候选四类场景操作，每类都有类型化合同、
   前置条件、幂等、验证和回滚语义；
4. 所有场景写入先进入 `ArtFlow_<run_id>` 隔离暂存层，源关卡不原地覆盖；Unreal 写入串行并
   使用事务，非 UE 资产准备可按依赖图并行；
5. 同机位回渲视觉评价与确定性三维技术检查并列；视觉分数不能覆盖保护对象、碰撞、边界、资源
   完整性和性能失败；
6. 纠正器只重做失败域，事件存储能从中断点恢复，外部执行结果未知时先对账而不是盲目重试；
7. ComfyUI 通过能力探测、已审阅子图目录和插槽编译器接入；`ComfyUI-Production-Nodes` 必须有
   真实 `/object_info` 和运行收据后才算集成；
8. 图生 3D 是可替换的实验资产 Provider；主闭环不依赖它，生成网格必须经过 Interchange、比例、
   面数、材质、碰撞、许可证和命名空间检查；
9. MCP 仅为现有类型化工具和资源提供薄适配，不拥有 Agent 状态机，不暴露任意代码执行；
10. 至少一条项目自有 UE 5.8 演示完成“概念图 → 灯光 + PCG 三维变更 → 同机位回渲 → 自动纠正
    → 发布”，并保留中文界面、流程截图、宿主证据和可重放收据；
11. 每个公开指标都给出数据集、分母和证据路径；规划中的能力与已验证能力严格区分；
12. 唯一下一切片、允许路径、停止条件和证据上限由 `config/goal-state.json` 决定。

## 持久编排结构

```text
Scene Analyst（只读事实）
  -> Visual Director（目标拆解）
  -> Scene Delta Planner（类型化 DAG）
  -> Material / Asset / PCG / Lighting Specialists（受限候选）
  -> Unreal Staging Executor（唯一写入通道）
  -> Visual Critic + Technical Judge（独立评价）
  -> Correction Planner（只修失败域）
  -> Publisher / Reconciler（发布、恢复、来源）
```

角色不是多个 Agent 自由聊天。每个角色只接收必要上下文，只能调用声明过的工具，并把结果写成
不可变事件或内容寻址 artifact。PydanticAI 可以承担类型化模型交互，但项目自己的 reducer、策略、
工具注册、恢复和评价仍是控制平面。

## 阶段顺序

```text
M7 Scene Digital Twin + Staged Scene Delta Kernel
  -> M8 ComfyUI Production Graph + PBR Material Route
  -> M9 PCG / Lighting / Asset Closed Loop
  -> M10 MCP Interoperability + Image-to-3D Experiment + Portfolio Release
```

M7 已完成扩展场景事实、灯光/PCG dry-run、候选关卡真实执行、同机位回渲、幂等对账以及发布/
丢弃回执。M8 又完成真实 RTX 4080 PBR 生成、逐通道拒绝、失败技术域纠正、UE 5.8 Material
Instance、Shader-ready 回渲和重复请求对账。M9-S1 又把材质、灯光、固定 PCG 图与项目资产复用
统一为类型化 Scene Delta DAG，验证了三路并行准备、单路 UE 写入、可选生成能力降级和 6/6 负对照。
当前 M9-S2 只负责把同一计划绑定真实 Twin、执行候选关卡四域变更并增加验证机位；纠正/发布、
图生 3D、MCP 和新前端分别保留在后续小切片，避免再次形成不可验证的大爆炸开发。

## 自主开发与停止边界

项目内候选选择、暂存层创建、项目自有演示场景修改、Codex 内置图像生成、同机位回渲、验证、
本地发布和已授权 GitHub 仓库更新由 Codex 负责，不设置人为权限门禁，也不要求用户代选结果。

只有以下情况允许停止并请求方向：目标会越出 ArtFlow 仓库或项目自有 UE 测试宿主；需要公开上传
未授权资产；会修改共享安装或无关用户数据；许可证不允许作品集用途；或唯一外部能力真实缺失且
没有项目内替代路线。正常测试失败、宿主启动、截图和候选质量波动都由开发循环自行处理。

测试优先覆盖合同、策略、重放、恢复和宿主边界，约占实现投入的 15–25%；不为追求测试数量延迟
真实 UE 闭环。前端在三维事件合同稳定后重做，必须中文、场景化、截图丰富，并展示真实状态而非
隐藏推理链。
