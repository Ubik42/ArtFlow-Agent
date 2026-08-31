# ArtFlow 产品路线

## 稳定底座（M0–M10，已完成）

项目已经验证持久事件与恢复、类型化能力和策略、Unreal Scene Digital Twin、隔离 Scene Delta、
ComfyUI PBR、PCG/灯光/材质/资产四域执行、独立技术与视觉评价、失败域纠正、薄 MCP 边界、实验
图生 3D 和中文案例发布。详细阶段证据位于 `docs/evidence/`；后续开发只在合同确有缺口时修改底座。

## 当前产品化路线

### M11 — Live Scene Session

- 用真实 Unreal 场景、简洁美术意图和可修改域创建 Session；
- 通过“场景变更谱”显示 Image / Material / Asset / PCG / Lighting 就绪度与依赖；
- 将只读草案持久化为事件，并生成内容寻址的候选暂存请求。

### M12 — Unreal editor bridge

- 从 UE 编辑器发起和恢复 Session；
- 在独立候选关卡串行执行注册工具，保留事务、回执和对账；
- 同机位回渲并返回技术检查和视觉评价。

### M13 — Cross-pipeline cases

- 把审阅 ComfyUI 图、GPT Image 2 开发生图、PBR、项目/生成资产、PCG 和灯光纳入同一编排；
- 用至少两个真实生产场景证明不同路由；
- 注入一个真实失败，只纠正失败域，不重做成功分支。

### M14 — Embedded delivery

- 完成 Unreal-facing 产品入口与中文使用路径；
- 冻结多案例素材、回执、截图、指标和复现命令；
- 形成克制、可独立验证的 GitHub 作品集发布。

## 取舍原则

- 先做最短真实纵向切片，再扩充能力面；
- 主流程不依赖图生 3D 或单一远程 Provider；
- UI 不建立平行状态机，不使用聊天壳、任意节点图或历史审批台作为核心交互；
- 75–85% 时间投入实现与真实宿主集成，测试集中在合同、幂等、恢复和外部边界；
- 当前唯一执行切片以 `config/goal-state.json` 为准，本文件只表达阶段方向。
