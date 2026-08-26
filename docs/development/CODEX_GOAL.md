# ArtFlow Agent 持续开发目标

## 产品目标

持续交付一个能够体现全面现代 Agent 工程能力、并真正服务游戏美术视觉迭代的 ArtFlow
Agent。模型负责受约束决策，手写 Harness 负责上下文、工具、策略、持久状态、审批、验证、
纠正、可观测性与评估；独立 sibling 仓库 Art Pipeline Skill 只是可按需调用的领域能力层，
不能与 ArtFlow 共用 Git、Python 包或 `/goal` 状态。

## 稳定完成定义

1. 一个真实 Unreal 场景包驱动本地 ComfyUI 与 Codex 内置 GPT Image 2 的同约束任务；
2. 自研事件状态机、SQLite 事件存储、上下文状态栏、能力注册、策略、完整性校验与恢复可检查；
3. PydanticAI 负责类型化模型交互，不替代项目自己的控制平面；
4. Planner、Router、Executor、Constraint Judge、Visual Critic 与 Recovery Planner 权限分离；
5. 每个工具声明作用域、风险、幂等、取消、验证和观察大小，未知状态不能冒充成功；
6. 前端真实呈现状态、工具、策略、评价分歧、恢复和证据，不展示隐藏思维链；
7. 冻结 Eval 与故障注入量化任务成功、约束违反、重复副作用、恢复、延迟和成本；
8. Codex 编排器依据持久化独立评价负责候选采用、局部修订和最终作品集交付；
9. C2PA 兼容交付可由独立验证器复核；
10. 当前证据等级在 `config/goal-state.json` 中如实记录。

正常闭环不设置人工批准点：项目内候选采用、局部修订、UE 回写验证与最终本地发布由 Codex
编排器负责。预览和证据检查只提供可见性，不能暂停执行。只有越出项目边界的不可恢复操作、
公共上传、共享安装或无可替代的外部能力缺失才允许中断并询问用户。

候选采用与最终本地发布不是人工轨道，也不得重新包装成“只读预览”审批。开发中若确需新增
视觉生成，只能由 Codex 编排器调用内置 GPT Image 能力并记录来源；不得接入第三方生图 API，
不得要求用户代选、代采用或代发布。

## 开发顺序

```text
Agent Kernel + Scene Package
  → Scene Lab + typed event UI
  → Unreal + 双 Provider 路由
  → Evaluation Tribunal + bounded revision
  → recovery / observability / eval
  → C2PA delivery + portfolio evidence
```

唯一下一切片、允许修改路径和停止条件以 `config/goal-state.json` 为准。
架构判断和反偏移规则以 `docs/AGENT_ENGINEERING_BLUEPRINT.md` 为准。
