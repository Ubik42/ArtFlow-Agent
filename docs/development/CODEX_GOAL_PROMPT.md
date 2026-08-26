# Codex `/goal` 启动提示词

> 用途：创建或替换 Codex 桌面长期 Goal。机器进度不复制到本提示词，始终从仓库状态恢复。

```text
持续开发 D:\3D\_tools\ArtFlow-Agent，把它交付为作品集中可真实演示的 ArtFlow AIGC Agent：
它从 Unreal/3D 场景事实和人类美术意图出发，通过手写现代 Agent Harness 完成上下文装配、
能力路由、策略与审批、生成执行、独立评价、失败纠正、人工采用、局部修订、回写和可验证来源。

【开始每轮前】
1. 先确认当前仓库是 D:\3D\_tools\ArtFlow-Agent，存在独立 .git，remote 为 ArtFlow-Agent；
   不得在 Codex 映射空目录、旧 D:\cs 路径或 sibling 仓库重建。
2. 完整读取根 AGENTS.md。
3. 运行 scripts/goal.ps1 -Action Resume，读取 config/goal-state.json、其 lastCheckpoint、
   docs/AGENT_ENGINEERING_BLUEPRINT.md、docs/development/CODEX_GOAL.md 和 CODEX_LOOP.md。
4. 检查 git status，保护用户和其他开发任务的脏工作树。
5. 运行 scripts/goal.ps1 -Action Doctor；只开发 nextSlice 声明的一个最短纵向切片，遵守
   allowedPaths、nonGoals、acceptance 和 stopConditions。

【不可混淆的仓库边界】
- 本仓是独立 ArtFlow AIGC Agent 和旗舰作品，拥有 Agent 状态、上下文、路由、审批、恢复、
  评价、人工采用、provenance 和 Scene Lab UI。
- D:\3D\_tools\art-pipeline-skill 是另一个独立 Git 与 /goal 的工具/资产审计 Skill；ArtFlow
  只能经版本化合同按需调用，不得吞入它的扫描器、Maya/Unreal 审计里程碑或机器状态。
- D:\3D\_tools\ComfyUI-Production-Nodes 是独立可安装运行时节点包，不复制进本仓。
- ArtFlow Unreal Bridge 保持独立安装，但其源码、构建和项目自有 disposable Unreal 宿主属于
  本仓正常开发范围，无需反复请求用户授权；不得借用或修改 sibling 仓库的测试宿主。

【产品与 Agent 工程目标】
- 核心产品是 Scene-to-Visual Production Control Plane，不是通用聊天壳、任意 ComfyUI
  画布生成器、框架教程或工具审计平台。
- 自研控制平面拥有 SQLite append-only events、deterministic reducer、Context Engine、
  Capability Registry、Policy/Approval、idempotency、interrupt、recovery 和 evidence lineage。
- PydanticAI 只负责类型化模型/工具调用与结构化输出，不成为状态库或策略权威。
- 模型只能选择注册能力和受审参数槽，不能生成任意 ComfyUI graph、执行任意宿主代码、
  自批费用、弱化用户约束或采用自己的结果。
- Planner、Router、Executor、Constraint Judge、Visual Critic、Recovery Planner 只有在权限、
  上下文或工具确实不同的时候分角色；禁止装饰性多 Agent 聊天。
- 生成与评价解耦；确定性失败不能被模型信心覆盖，评价分歧与不确定性必须可见。
- Context 使用稳定前缀、代码生成状态栏、来源标记、Artifact 化大输出和保留约束/决定/失败/
  引用的压缩。检索内容是数据，不能授权动作。
- 生产记忆分 episodic/semantic/procedural，所有共享记忆更新均有来源、冲突检查和激活审批。
- UI 是 Scene Lab + Agent Flow，呈现真实状态、工具、审批、恢复、评价和证据，不展示隐藏思维链。
- OpenTelemetry、MCP、AG-UI、C2PA 按蓝图作为观测/互操作/来源边界；不为技术名词堆框架。

【开发节奏与验证】
- 75–85% 用于实现和真实纵向集成，15–25% 用于高价值验证。
- 开发中只跑当前切片最窄的 schema/lint/unit/contract；里程碑边界再跑完整后端、前端 build
  和必要浏览器验收。不追覆盖率，不为 trivial adapter 堆 mock matrix。
- 测试重点：合同兼容、非法状态迁移、审批失效、幂等、重启重放、未知完成、恢复、外部解析。
- 每个公开数字必须说明冻结任务集、分母、命令和持久证据；不把 schema、mock、截图、
  单次成功或模型自述升级成真实能力。
- acceptance 全部通过后才更新 goal-state、写下一个 checkpoint，并运行 Goal Audit。

【安全与自主开发】
- 保留真实 run 862ac768a2f2：它有三个 RTX 4080 候选、仍在 review、没有人工选择；不得代用户
  选择、重生成、批准、修订或改写历史。
- 项目内 GPU/ComfyUI 生成、Codex 内置 GPT Image 2、生图结果筛选采用、作品集打包与本地交付
  均自主推进，不得再次向用户索要授权；不走需要密钥或付费确认的直接 Provider API 主线。
- 超时/取消不等于外部动作未发生；unknown/unsupported 不得记为成功；执行结果需要独立验证。
- 普通只读诊断、代码实现和当前 nextSlice 内可恢复写入自主推进，不反复请求确认。
- 只有修改无关现有工程、共享安装或目标发生实质歧义时才暂停；不得把 GPU、艺术选择、候选采用、
  作品集交付或 Agent 自己添加的保守假设升级为人工门禁。

【持续性】
不要依赖聊天记忆判断进度。每次自动续跑都重新 Resume/Doctor，以当前代码、测试、artifact、
goal-state 和 checkpoint 为事实。用户的新指令可以替换下一切片，但必须把改变写回权威状态，
防止后续 Goal 漂移。持续推进直到 docs/development/CODEX_GOAL.md 的完成定义和真实作品集证据
全部满足；不要因为工作量大、上下文压缩或一次失败而提前结束。
```
