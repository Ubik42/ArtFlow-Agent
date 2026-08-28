# ADR-0004：Unreal Scene Delta 编排与 MCP 边界

- 状态：Accepted
- 日期：2026-08-27
- 决策者：ArtFlow Agent 项目

## 背景

M0–M6 已证明 Unreal 场景采集、二维候选生成、独立评价、持久恢复与可验证回流，但当前回流只是
把二维结果作为预览材质绑定到平面，不能代表二维视觉意图已转化为三维场景。下一阶段还需要接入
PCG、灯光、PBR 材质、三维资产和外部 Agent 宿主。如果每个能力都直接写 Unreal，或让模型生成
任意画布/脚本，已有的权限、恢复和证据工程会失效。

## 决策

### 1. 采用 Scene Digital Twin 与 SceneChangePlan

扩展现有 `scene-constraint-package/1`，以不可变 Scene Digital Twin 表达三维事实。所有写操作先被
规划为版本化 `SceneChangePlan` DAG。计划节点只允许来自注册表的判别联合类型，包含：

- `operation_id`、`operation_type`、`depends_on`；
- `target_selector` 与 `expected_source_fingerprint`；
- 类型化参数、确定性种子和预算；
- `write_scope`、`idempotency_key`、验证器和补偿/清理动作。

模型提出计划；确定性策略验证并冻结计划；Executor 只执行冻结后的节点。

### 2. 所有 Unreal 变更先进入暂存环境

优先使用运行专属 Data Layer，后备使用 Level Instance 或项目内候选关卡。源 Actor 默认只读，
只有显式可编辑且指纹匹配的对象才能被操作。资产写入 `/Game/ArtFlow/Generated/<run_id>`；导入、
场景写入与发布各自生成 receipt。发布与丢弃都是类型化操作。

### 3. 一个持久协调器，多种受限角色

角色共享的是 artifact 引用和事件，不共享自由聊天记录。Material、Asset、PCG、Lighting 分支可以
并行准备；Unreal Executor 是唯一串行写入通道。Judge 和 Critic 只读，不能采用自己的结果。

### 4. MCP 是薄适配器

ArtFlow 内部端口、Pydantic/C++ schema、策略和事件状态机为源。MCP Resources/Tools 从这些合同
派生，并把调用重新送入同一执行管线。禁止 MCP 暴露任意 Python、Shell、Blueprint、文件路径或
ComfyUI workflow JSON。MCP Server 不维护第二份运行状态。

### 5. ComfyUI 使用受审阅子图编译

技术美术维护版本化子图和能力 manifest；Agent 只选择子图和填写插槽。自定义节点只有在运行时
能力探测与真实收据验证通过后才能进入 manifest。画布可视化用于作者和调试，不是 Agent 权限面。

### 6. 图生 3D 是可替换候选 Provider

`asset.mesh.generate` 统一封装本地或远程实现。结果必须经过许可证、哈希、Interchange、比例、
几何、材质、碰撞和预算验证后，才能加入暂存资产集合。主闭环必须在该 Provider 不可用时继续。

## 后果

正向结果：

- Agent 复杂度落在可展示的规划、依赖、权限、恢复、评价与纠正上；
- Unreal、ComfyUI、Codex 和未来模型可以替换而不改权威状态；
- 每次变更都能回放、比较、丢弃或发布；
- MCP 带来互操作而不扩大宿主执行面。

代价：

- 需要先建设 Scene Digital Twin、SceneChangePlan 和 UE staging，再看到完整生成效果；
- Data Layer 与非 World Partition 关卡需要两种暂存实现；
- 导入不总能依赖 Undo，必须实现清理和内容寻址命名；
- 图生 3D 质量与许可证需要 Provider 级证据，不能作统一承诺。

## 被否决方案

- **模型直接操作 Unreal Python/Blueprint**：权限面过宽、难以恢复和验证；
- **MCP 作为内部工作流引擎**：会形成双状态机并削弱既有 Harness；
- **让 Agent 任意生成 ComfyUI/PCG 图**：把任意代码和节点供应链风险带入运行时；
- **先接入所有 3D 模型再做场景合同**：主线会被硬件、许可证和模型质量牵引；
- **继续把二维贴图平面当成 UE 回流终点**：无法证明真实三维场景编排能力。
