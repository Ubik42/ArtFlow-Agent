# Codex `/goal` 持续开发提示词

> 用于创建或替换 Codex 长期 Goal。阶段进度不写死在提示词中；每轮均从仓库机器状态恢复。

```text
持续开发 D:\3D\_tools\ArtFlow-Agent，将 ArtFlow 交付为可实际操作、可在作品集中完整演示的
Unreal 场景导演 Agent。它从当前 Unreal 场景和美术意图出发，把图像、PBR、资产、PCG、灯光
等能力编排成类型化 Scene Delta，在隔离候选关卡中执行、回渲、独立评价、只纠正失败域，最后
发布可恢复、可追踪的场景变更。

【每轮恢复】
1. 确认仓库、独立 Git 和 remote；读取根 AGENTS.md。
2. 运行 scripts/goal.ps1 -Action Resume 和 -Action Doctor，读取 config/goal-state.json、
   lastCheckpoint、CODEX_GOAL.md、CODEX_LOOP.md 及可观察代码/证据。
3. 检查工作树并保护用户已有修改。只实施 nextSlice 的最短真实纵向切片；接受条件通过后才更新
   goal-state、checkpoint 和下一个切片。聊天摘要不是进度事实。

【产品北极星】
- 产品是 Unreal 原生实时场景导演工作区，不是图片生成器、聊天壳、任意节点画布、工具审计台
  或通用 AI 仪表盘。
- 使用者从真实 Scene Session 发起任务：检查场景 → 表达视觉意图 → 选择允许改变的域 → 查看
  类型化 Scene Delta → 在候选层执行 → 同机位回渲 → 技术与视觉独立评价 → 纠正/发布。
- 每个已验证的宿主阶段最终都必须收敛为 Unreal 或场景导演台中的产品入口；命令行与一次性脚本
  只可用于开发验证，不得被 README 包装为最终操作体验。
- UI 使用 ArtFlow 自己的“场景变更谱”语言：像调色、混音与虚拟制片导演台，场景媒体优先，
  管线显示为有节奏的变更轨道；避免霓虹 AI 控制室、伪终端英文、卡片墙和夸张营销口号。
- 中文为主要产品与公开文档语言；README 克制呈现产品、能力、真实案例和复现方法，不写开发
  对话、提示词、权限争论或“AI 帮我们做了什么”。

【Agent 工程约束】
- 项目自己的 append-only events、deterministic reducer、Context Engine、Capability Registry、
  typed tools、policy、idempotency、reconcile、evaluation 与 provenance 是唯一控制平面。
- PydanticAI/MCP/AG-UI/OpenTelemetry/C2PA 仅在解决明确边界时使用，不得形成平行状态机或
  技术名词堆砌。MCP 是现有窄工具的薄适配，不暴露任意代码执行。
- 模型只选择已注册能力和受约束参数，不能生成任意 Blueprint、Python、Shell、C++、ComfyUI
  graph，不能修改保护对象，也不能用自评分覆盖确定性失败。
- 生成者、Constraint Judge、Visual Critic、Recovery Planner 和 Publisher 只有在上下文、权限
  或工具确实不同时才分角色；角色通过事件和类型化 artifact 协作，不做装饰性群聊。
- Scene Digital Twin 是场景事实；所有 Unreal 写入先进入项目自有候选层并串行执行。超时不等于
  未执行，未知完成先 reconcile；失败只重做受影响分支。
- ComfyUI-Production-Nodes 是独立运行时节点包，通过版本化能力清单、真实 /object_info、审阅
  子图与插槽编译器接入，不复制代码、不允许模型任意拼图。图生 3D 始终只是候选 Provider。

【自主范围和真实边界】
- 当前仓库、项目自有 UE 宿主、项目内候选采用、局部修订、GPU/ComfyUI 任务、Codex 内置
  GPT Image 2 开发期生图、截图、打包和已经配置的 GitHub 更新均由 Codex 自主完成，不设置
  浏览、展示或“再确认一次”的人为门禁，也不让用户代为选择候选。
- 只有真正越出仓库和项目自有宿主、修改共享安装/无关数据、上传未授权素材、产生未约定外部
  费用或需要用户独有登录态且无替代路线时暂停。外部隐私/费用约束是能力策略，不得污染本地
  产品主流程或变成作品集中的审批弹窗。
- 采用和发布必须引用持久评价、策略版本、场景身份和候选身份；自主不等于无证据。
- 当前 Session 的正常路径不得读取 M13–M16 固定评价或展示谱系；这些只保留为兼容夹具。每次评价、
  纠正、采用与发布都必须从当前工作项、当前回执和当前内容哈希重新建立身份链。

【快速开发纪律】
- 每个切片以一个真实可演示闭环为目标，75–85% 时间用于实现与宿主集成，15–25% 用于验证。
- 开发中只跑受影响的 schema/lint/unit/contract 和一次目标尺寸视觉检查；里程碑边界才跑完整后端、
  前端 build、真实 UE/ComfyUI 回执与截图。不追覆盖率，不为简单适配器堆 mock matrix。
- 不因历史架构而继续扩展失效入口；发现过期文档、死样式、重复 fixture 或已经完成却仍标 active
  的状态时，在当前切片允许范围内直接清理并留下迁移说明。
- 优先完成一条从项目自有场景到 Published 版本的连续可录制路径，再扩展新的 Provider、领域或
  架构名词；同一能力不得同时存在两套状态机、两套发布器或两个事实来源。
- 已实现、实验性、计划中必须分开。任何公开数字都绑定任务集、分母、命令和持久证据；截图和
  schema 不能冒充宿主能力。

持续 Resume → Implement → Focused Verify → Checkpoint → Advance，直到 CODEX_GOAL.md 的完成定义
全部由真实 UE/ComfyUI 回执、中文流程截图和可复现发布包满足。不要因上下文压缩、一次宿主失败
或工作量大而结束，也不要越过 nextSlice 同时铺开多个半成品方向。
```
