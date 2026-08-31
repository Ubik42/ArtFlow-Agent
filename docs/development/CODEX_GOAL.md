# ArtFlow Agent 持续开发目标

## 当前目标

ArtFlow 是 **Unreal 原生的二维视觉意图到可验证三维场景变更 Agent**。当前开发从已经验证的
技术底座进入产品化阶段：把只读案例与证据界面推进为真正可操作的实时 Scene Session，让用户
从引擎场景发起任务，编排受限管线，并在候选关卡完成执行、评价、纠正和发布。

M0–M11 已建立持久事件、类型化工具、真实 Unreal Scene Digital Twin、ComfyUI PBR、四域 Scene
Delta、失败域纠正、MCP 边界、实验图生 3D、持久 Scene Session 和“场景变更谱”。M12 已完成
真实 UE 5.8 编辑器握手、请求派生候选关卡、注册 PCG/灯光工具执行、同机位回渲和新进程对账，
并证明源关卡字节不变。M13 已完成 ComfyUI PBR 全管线案例和 GPT Image 2 视觉目标案例，后者
真实验证了只纠正 lighting、四个成功域证据哈希不变。M15 已把通过复检的精确候选正式采用并
发布为内容寻址 Unreal 场景变体，新进程对账没有重复关卡包。M16 已把纠正、采用、发布与 UE
审阅组织成六段场景变体谱系，并完成桌面与窄屏实测。M17 已将评价、采用、发布和审阅写入
同一条 Scene Session 事件流；M18 已完成 Unreal 原生注册回调。M19 已将实时导出的当前场景编译为
可由 Unreal 原子领取的候选工作项，执行、对账和结果直接返回场景变更谱。这些能力作为稳定底座保留，后续不重复
造轮子，也不再以历史审批/证据控制台作为产品主叙事。

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

- **M11 · Live Scene Session and Scene Change Spectrum（已完成）**：真实场景、意图和域选择已经能
  编译为确定性内容寻址草案，持久 Session 与候选暂存请求已进入“场景变更谱”。
- **M12 · Unreal editor session bridge and candidate execution（已完成）**：UE 编辑器可发起 Session，
  在请求派生候选关卡执行注册工具、回渲并跨进程对账，重启没有重复 PCG 实例或源关卡写入。
- **M13 · Cross-pipeline transformation and correction（已完成）**：雨后庭院由当前 ComfyUI PBR
  驱动多域联合候选；晴光庭院由 GPT Image 2 定义视觉目标，并在单一 lighting 失败后只执行灯光补丁。
- **M14 · Embedded delivery and portfolio release（已完成）**：中文只读展示可在 clean clone 中一键
  启动，两条当前案例、Unreal 入口、流程截图、教学文档和 49 文件可验证发布包已对齐。
- **M15 · Evidence-bound disposition and versioned Unreal publish（已完成）**：由编排器基于持久评价
  证据决定采用，把合格候选发布为版本化 Unreal 场景变体，并在新进程完成幂等对账。
- **M16 · Scene Variant Ledger and embedded Unreal review（已完成）**：把评价、定向纠正、采用与
  发布组织为“场景变体谱系”，并提供只指向精确 Published 版本的 Unreal 审阅入口。界面延续领域
  光谱，但加入空间化场景框、版本胶片和明确发布刻度，避免聊天框、节点画布和通用 AI 仪表盘。
- **M17 · Durable live scene-variant lifecycle（已完成）**：候选评价、纠正、采用、发布和审阅已
  纳入现有 append-only Scene Session 事件与 Reducer；当前运行投影实时谱系，冻结展示数据仅作演示回退。
- **M18 · Unreal-native lifecycle callback（已完成）**：Unreal 以内容身份回传评价、采用、发布和审阅，
  服务端解析项目注册制品并按顺序写入同一事件流；回调不接收主机路径，重放不会重复事件。
- **M19 · Live candidate execution and progress（已完成）**：已封存 Candidate Plan 成为当前 Session
  的注册工作项；Unreal 菜单可领取单一写入权，执行、对账与结果由同一事件流投影。
- **M20 · Current-session tribunal and correction（进行中）**：从当前工作项的真实回渲与三维回执生成
  独立评价，失败时只编译失败领域补丁，通过时进入采用与发布，不再读取 M16 历史评价制品。
  当前成功工作已完成六项内容绑定技术审查；同源视觉裁决保留 image 与 PCG，只标记 lighting 失败。
  下一步由 Unreal 对现有候选执行一次内容绑定灯光补丁并回渲复评。

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
