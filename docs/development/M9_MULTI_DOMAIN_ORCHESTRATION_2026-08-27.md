# M9：二维视觉意图到多域 Unreal Scene Delta 的 Agent 编排

## 产品目标

M9 不再把材质、PCG、灯光和资产生成做成四个互不相干的按钮，而是让 Agent 把一张概念图解释为
一个有依赖、有预算、可回滚的三维变更提案。最终交付物不是图片，而是 Unreal 候选关卡中的
`Scene Delta`、同机位/验证机位回渲、技术判定和发布回执。

二维图无法唯一反演三维场景。因此系统采用“可解释的最小变更”策略：优先调已有参数和复用项目
资产，其次生成材质与 PCG 布局，只有现有资产无法满足轮廓时才请求可选图生 3D Provider。

## 编排结构

```text
Scene Digital Twin + Concept Target
  → Scene Analyst：读取相机、对象、材质、灯光、PCG、边界、保护关系
  → Visual Director：把视觉意图拆为材质 / 布局 / 灯光 / 资产目标与不确定性
  → Delta Planner：生成类型化依赖 DAG、预算、前置条件和验证计划
  → Capability Router：按真实能力、许可证、成本和宿主状态选择执行面
      ├─ Material Specialist → 受审 ComfyUI 子图 / GPT Image 2 → PBR 合同
      ├─ Layout Specialist   → 固定 PCG Graph + 参数/种子/边界
      ├─ Lighting Specialist → 灯光/雾/后处理的白名单属性差量
      └─ Asset Specialist    → 项目资产检索；必要时生成 GLB 候选并过 Interchange
  → Unreal Staging Executor：唯一串行写入者，Data Layer 或候选关卡
  → Technical Judge + Visual Critic：三维硬约束与多机位视觉评价相互独立
  → Correction Planner：只重做失败域，不重放已成功分支
  → Publisher / Reconciler：发布、丢弃、崩溃对账和完整来源链
```

这些 Specialist 是同一 durable runtime 中的有界角色，不是多个模型自由聊天。它们共享内容寻址
artifact，不共享隐式思维过程；模型不能生成 Python、Blueprint、C++、任意 PCG 图或任意 ComfyUI
workflow。

## 工具面与合同

首批工具保持窄而可组合：

| 工具 | 作用 | 关键边界 |
| --- | --- | --- |
| `scene.twin.read` | 读取场景事实与保护关系 | 只读 Resource；按 hash 固定输入 |
| `scene.delta.plan` | 编译依赖 DAG | discriminated union；禁止脚本字段 |
| `material.pbr.prepare` | 生成/纠正五通道材质 | 只能选择受审模板和有限插槽 |
| `pcg.instance.configure` | 设置固定 Graph Instance 参数 | 图路径 allowlist、确定性种子、边界预算 |
| `lighting.rig.patch` | 修改白名单灯光/雾/后处理属性 | 数值范围、依赖和保护对象门禁 |
| `asset.catalog.query` | 查询项目可复用资产 | 许可证和来源元数据必填 |
| `asset.mesh.admit` | 导入候选 GLB/USD | Interchange、比例、面数、UV、材质、碰撞检查 |
| `ue.stage.apply` | 串行应用 Scene Delta | 内容寻址、前置哈希、事务与清理策略 |
| `ue.stage.render` | 固定机位和验证机位回渲 | 等待资产/Shader 编译，输出不可变收据 |
| `scene.delta.judge` | 技术/视觉独立评价 | 硬失败不能被视觉分覆盖 |
| `scene.delta.publish` | 发布或丢弃 | 只接受已验证 stage id；重复调用对账 |

MCP 在 M10 只把 `scene.twin.read` 等只读事实映射为 Resources，把上述窄动作映射为 Tools；其 schema
从现有 Pydantic/C++ 合同生成。MCP 不拥有状态机、记忆、策略或发布权，也不提供 `run_python`、
`execute_blueprint`、`submit_workflow_json` 一类开放工具。

## 为什么采用 UE 原生 PCG 而不是让模型画任意图

UE 5.8 已提供可描述、可分组的 Graph Parameters、Graph Instance、Editor/headless generation、缓存与
调度改进，并支持非破坏性手工覆盖。项目因此维护少量经过技术美术审阅的 PCG 模板，Agent 只填写
资产集合、密度、种子、坡度/高度范围、排除区和 Data Layer。World Partition 场景可让 PCG 生成物
继承 Data Layer；非 World Partition 测试宿主继续使用内容寻址候选关卡。

这既保留“画布式管线”的可解释性，也把运行时自由度限制在可验证参数，而不是让模型获得任意
Blueprint 节点或 `Execute Blueprint` 能力。

## M9 实施切片

### M9-S1：多域 Scene Delta 合同与 dry-run 编排

- 将材质、灯光、PCG 和项目资产复用统一为一个依赖 DAG；
- 建立 Capability Router、分支预算、前置条件和失败域分类；
- 用固定废墟祭坛目标生成 dry-run，证明材质完成后 PCG/灯光可独立准备、UE 写入仍严格串行；
- 加入恶意脚本字段、保护对象目标、未审 PCG 图和预算超限负对照。

### M9-S2：真实联合执行与多机位判定

- 在项目候选关卡应用已验证材质、PCG 参数和灯光 patch；
- 增加同机位 beauty 与至少一个验证机位，检查遮挡后结构、碰撞、边界和 Actor 数；
- 技术 Judge 与 Visual Critic 独立出具证据，纠正器只重做失败分支。

### M9-S3：发布、丢弃、恢复与作品证据

- 证明中断恢复不重复生成、不重复导入、不重复生成 PCG Actor；
- 发布或丢弃完整 Scene Delta，源关卡与保护对象保持不变；
- 输出中文场景化 UI 状态、UE 截图、流程图和可重放演示材料。

## 一手资料核对（2026-08-27）

- UE 5.8 Release Notes：PCG 新增非破坏性手工编辑、复杂参数、嵌入子图、Graph Parameters 编辑器、
  缓存/调度和 ISM 复用改进；这些能力适合作为“受审图 + 类型化参数”的执行面。
- UE 5.8 PCG Editor/API：Tool Graph 暴露参数覆盖，`UPCGEngineSubsystem` 支持 Editor/headless 生成，
  Graph Instance 是组件参数写入入口。
- UE 5.8 PCG + World Partition：Spawn Actor/Create Target Actor 可继承或显式指定 Data Layer。
- UE 5.8 Interchange：格式无关、异步、可定制 Pipeline Stack；GLB/glTF/USD 可按文件类型选择管线，
  reimport 会保留原管线与选项。
- Comfy API v2：poll-first、可恢复、幂等提交、UUID 任务和内容寻址资产，适合做执行器而非状态机。
- MCP 2025-06-18：Resources 是上下文、Tools 是模型可调用动作；HTTP 授权要求 audience-bound token，
  禁止 token passthrough。ArtFlow 本地 STDIO facade 不复制 OAuth 状态，远程部署再启用完整授权。
