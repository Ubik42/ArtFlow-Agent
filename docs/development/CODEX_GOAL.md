# ArtFlow Agent 持续开发目标

## 当前目标

ArtFlow 是 **Unreal 原生的二维视觉意图到可验证三维场景变更 Agent**。当前开发从已经验证的
技术底座进入产品化阶段：把只读案例与证据界面推进为真正可操作的实时 Scene Session，让用户
从引擎场景发起任务，编排受限管线，并在候选关卡完成执行、评价、纠正和发布。

M0–M10 已建立持久事件、类型化工具、真实 Unreal Scene Digital Twin、ComfyUI PBR、四域 Scene
Delta、失败域纠正、MCP 边界、实验图生 3D 和第一版中文作品集证据。这些能力作为稳定底座保留，
后续不重复造轮子，也不再以历史审批/证据控制台作为产品主叙事。

## 产品闭环

```text
Unreal 当前场景
  → Scene Session（场景事实 + 美术意图 + 可修改域）
  → Scene Change Spectrum（能力就绪度、依赖和边界）
  → Typed Scene Delta（材质 / 资产 / PCG / 灯光 / 图像目标）
  → Unreal Candidate Stage（唯一串行写入通道）
  → Same-camera Rerender + Technical Judge + Visual Critic
  → Failed-domain Correction
  → Reconciled Publish + Provenance
```

## 阶段路线

- **M11 · Live Scene Session and Scene Change Spectrum**：把真实场景、意图和域选择编译成确定性、
  内容寻址的只读草案，并形成 ArtFlow 自有的“场景变更谱”交互语言；随后持久化 Session 并生成
  候选暂存请求。
- **M12 · Unreal editor session bridge and candidate execution**：从 UE 编辑器发起 Session，在项目
  自有候选关卡执行注册工具、回渲并对账，证明重启与重试没有重复副作用。
- **M13 · Cross-pipeline transformation and correction**：将审阅过的 ComfyUI、GPT Image 2 开发编排、
  PBR、项目/生成资产、PCG 与灯光纳入同一计划，用多个真实生产案例证明路由和失败域纠正。
- **M14 · Embedded delivery and portfolio release**：完成 Unreal-facing 入口、中文产品界面、多个可复现
  案例、流程截图、教学文档和可验证发布包。

具体唯一下一切片、允许路径、风险、停止条件和证据上限由 `config/goal-state.json` 决定。

## 完成定义

1. 用户能从项目自有 UE 5.8 演示场景直接创建 Scene Session，而非先操作内部测试夹具。
2. Agent 从 Scene Digital Twin 与显式意图生成版本化 Scene Delta；模型不能生成宿主代码或任意图。
3. Image、Material、Asset、PCG、Lighting 至少四类能力能按真实就绪度路由；ComfyUI 通过审阅子图
   和版本化节点能力接入，图生 3D 可缺席而不阻塞主闭环。
4. 所有写入先进入项目自有候选层，源关卡不原地覆盖；外部结果未知时先对账，不盲目重试。
5. 同机位视觉评价与确定性三维检查相互独立；保护对象、碰撞、边界、资源和预算失败不可被覆盖。
6. 至少两个差异明显的模拟真实生产案例完成“意图 → 多域变更 → 回渲 → 评价 → 纠正/发布”，且
   其中一个真实注入失败并只重做失败域。
7. UI 以中文“场景变更谱”和真实媒体构成可辨识的导演工具，不是聊天、节点画布、AI 仪表盘或
   伪终端；桌面与窄屏均完成目标尺寸验收。
8. README、使用文档和发布包以克制的作品集语言呈现，包含大量真实流程截图，所有能力与数字都
   能定位到冻结回执、任务分母和复现命令。

## 开发纪律

- 一次只完成一个最短真实纵向切片；75–85% 实现，15–25% 高价值验证。
- 测试重点是合同、非法状态迁移、幂等、未知完成、恢复与宿主边界；不追覆盖率或浏览器矩阵。
- 本仓、项目自有 UE 宿主、候选采用、Codex GPT Image 2 开发生图、截图、打包和已配置 GitHub
  更新属于自主开发范围。真正的外部费用、隐私和共享安装边界由策略处理，不制造虚假权限门禁。
- Planner、Specialist、Judge、Critic、Recovery 与 Publisher 仅按真实权限/上下文隔离；所有协作
  通过不可变事件和类型化 artifact，不通过表演式多 Agent 对话。
- 每轮从 goal-state 和 checkpoint 恢复。接受条件满足后立即记录证据并切换下一切片，避免目标漂移。
