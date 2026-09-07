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
- **M20 · Current-session tribunal and correction（已完成）**：从当前工作项的真实回渲与三维回执生成
  独立评价，失败时只编译失败领域补丁，通过时进入采用与发布，不再读取 M16 历史评价制品。
  双灯光组实测通过后已由 Codex 采用精确内容身份。
- **M21 · Current-session publish and review（已完成）**：当前采用决定已接入已有版本化发布合同；
  Unreal 写入唯一内容寻址 Published 版本，新进程完成发布与审阅对账，源关卡字节未变化。
- **M22 · Unreal-native operator lifecycle controls（已完成）**：发布与审阅合同已接入 Unreal
  中文 Tools 菜单；编辑器重启后可从项目持久指针恢复受验证的 Scene Session，公开菜单只保留
  四个产品生命周期入口。恢复不接受调用方 Run、路径或脚本，源关卡身份不一致时关闭失败。
- **M23 · Blender DCC production bridge and Unreal return（已完成）**：优先接入本机 Blender 5.2
  LTS，把它作为建模、Geometry Nodes、ComfyUI PBR 装配与 Bake、场景布局、相机灯光和后续模拟
  缓存的完整 DCC 执行面。模块化建筑道具生成，以及受审 ComfyUI PBR 到 Blender 可编辑材质、
  嵌入式 GLB、预览图和 Unreal Interchange 候选回流均已真实完成，并已提升为 Scene Session
  中可派发、领取、对账和重放的持久工作项。Geometry Nodes 多资产庭院已根据 Session 边界
  真实生成并回流新的 Unreal 候选；Unreal 当前相机与灯光也已驱动 Blender 同机位预演，并把
  有界 key / fill / rim 灯光方案对账回新的候选关卡。四段固定能力现已接到产品内的 Session
  DCC Worker，用户从场景变更谱派发并启动后，领取、执行、对账与结果都进入原有事件流。
- **M24 · Scene-conditioned ComfyUI production route（已完成）**：把 ComfyUI 节点生态用于真实
  场景条件生成。优先接入 Unreal Depth / World Normal / Object ID 与 Production Nodes 的版本化
  ControlNet/LoRA/PBR 子图，让 Agent 编译类型化参数并把输出继续交给 Blender/Unreal，而不是
  在产品中开放任意 workflow 编辑或把 ComfyUI 变成第二套控制平面。当前实机没有 ControlNet/LoRA
  权重，首条路线已根据运行时事实选择 FLUX.2 `ReferenceLatent`：固定预处理器融合 Unreal Beauty
  与有效范围 Depth，真实生成结构保持的暖色光照目标。该目标现已继续编译为三组登记材质色板与
  key / fill / rim 参数，在 Blender 5.2 生成可编辑 lookdev 预演并回流 Unreal 5.8 隔离候选；
  重复执行完成对账且源关卡字节不变。
- **M25 · DCC capability graph and live dispatch（已完成）**：把已经实测的建模、ComfyUI PBR、
  Geometry Nodes、镜头灯光和场景条件 lookdev 统一成当前 Scene Session 的生产能力图。Blender
  继续作为覆盖 UV、材质节点、Bake、布局、灯光及后续缓存的完整 DCC 执行面；ComfyUI 以受审
  节点子图参与图像、控制图和材质生成；Unreal 始终通过候选关卡接收结果。当前最短切片先把
  scene-conditioned lookdev 已接入已有 DCC Worker 与产品状态投影，没有新增编排器。当前工作项
  依次记录 queue / claim / execute / reconcile / success，场景变更谱显示目标图、Blender 预演与
  Unreal 候选三段真实媒体。
- **M26 · Surface authoring and bake round-trip（已完成）**：扩展 Blender 的非建模生产能力，
  从当前 Lookdev `.blend` 编译有界 UV 与材质 Bake 任务，生成可复用贴图和带 UV 的交换资产，
  完成最小 UV/贴图/材质槽检查后回到新的 Unreal 隔离候选。Blender 5.2 已实际生成 1024²
  Base Color / Roughness、命名 UV、单材质 GLB 与可编辑 `.blend`；Unreal 5.8 导入网格、材质和
  两张纹理，重复回流对账且源关卡字节不变。
- **M27 · Live surface capability dispatch（已完成）**：把已经实测的 Surface Bake 提升为当前
  Scene Session 的第六项 DCC 能力，复用现有 DCC Worker 的 queue / claim / execute / reconcile
  生命周期，并在场景变更谱展示 Lookdev、UV 图集、Blender 结果和 Unreal 候选之间的连续关系。
  桌面与窄屏产品检查均无横向溢出，四张真实媒体成功加载，控制台错误与警告为 0。
- **M28 · Physics-assisted set dressing round-trip（已完成）**：继续使用 Blender 的非建模能力，
  把当前场景边界、登记原型、确定性种子和有限帧预算编译为刚体散落任务。Blender 负责求解并返回
  可编辑 `.blend`、预览和变换清单；Unreal 只在新的隔离候选中应用经过边界检查的最终变换。
  当前实测 12 个实例在第 96 帧稳定，重复回流对账且源关卡不变。
- **M29 · Live set-dressing dispatch（已完成）**：把刚体布景登记为 Scene Session 的第七项 DCC
  能力，复用已有 Worker 与事件账本，并在场景变更谱展示 Surface 输入、物理解算、变换清单和
  Unreal 布景候选之间的连续关系。
- **M30 · Scene-conditioned surface detail projection（已完成）**：把 ComfyUI 的节点式生成用于
  引擎表面细节，而不止用于概念图。Agent 从当前 Unreal 机位、对象身份和有界区域选择登记的
  ComfyUI 子图生成贴花/表面细节，Blender 负责投射、UV、材质与烘焙，Unreal 接收可编辑材质
  候选。当前真实链路生成一次后持续复用同一内容身份，重复 Unreal 回流没有创建或更新 Actor，
  源关卡保持不变。
- **M31 · Live surface-detail dispatch（已完成）**：把 M30 的请求、ComfyUI 回执、Blender 编辑源、
  烘焙结果和 Unreal 候选登记为当前 Session 的第八项 DCC 能力，接入现有 queue / claim /
  execute / reconcile 生命周期与场景变更谱，不增加调度器或确认门禁。
- **M32 · Cross-host procedural scene assembly（已完成）**：已完成“视觉方向 → 模块/材质 → PCG
  布局 → 同机位回渲”的短闭环。当前场景边界和已登记的 ComfyUI 表面目标被编译为三变体
  Wayfinder 套件；Blender 5.2 保留 Geometry Nodes recipe、UV、双材质槽、LOD1 与碰撞元数据，
  Unreal 5.8 将九个确定性点位写入新的隔离候选。三项资产均有 2 级 LOD 和 1 个简单碰撞体；
  重复回流创建与更新对象均为 0，源关卡不变。
- **M33 · Live procedural assembly dispatch（已完成）**：把 M32 的精确请求、Blender 套件回执、
  清单和 Unreal 候选登记为当前 Session 的第九项 DCC 能力，继续复用现有 Worker、事件账本和
  场景变更谱。界面以艺术目标、DCC 加工、PCG 装配和候选结果四段真实媒体表达路线；桌面与
  窄屏均无横向溢出、失败媒体或控制台消息。
- **M34 · Scene-conditioned native PCG density（已完成）**：节点工作流已经用于场景空间数据。
  Agent 从当前 Unreal Depth 与保护区编译固定 ComfyUI 密度蒙版任务，将输出投影为 12 个类型化
  空间点；项目自有 Unreal PCG 图消费这些点和 M32 的三种模块资产，在隔离候选中生成 12 个
  原生实例。重复执行完成对账，保护区泄漏、重复副作用和源文件变化均为 0。
- **M35 · Live native PCG route（已完成）**：把 M34 的精确场景输入、ComfyUI 回执、空间清单、
  原生 PCG 图与 Unreal 候选登记为当前 Session 的第十项生产能力，复用现有 Worker 和事件账本，
  并在场景变更谱中呈现“场景条件 → 节点密度 → Blender 套件 → 原生 PCG 候选”。
- **M36 · Shot-ready procedural environment package（已完成）**：把当前视觉目标、Blender 镜头与
  灯光预演、原生 PCG 候选编译为可直接交付镜头部门的 Unreal Level Sequence 候选，包含登记的
  CineCamera、有限灯光参数、PCG 场景版本和同机位预览，不另建调度器或开放任意 Sequencer 脚本。
- **M37 · Live shot-package dispatch（已完成）**：把 Shot Package Request、Blender Shot Receipt、
  Level Sequence 与 Unreal 候选回执登记为当前 Session 的第十一项生产能力，复用既有 Worker、
  事件账本和场景变更谱，形成从视觉方向到可交付镜头资产的连续产品路线。
- **M38 · Bounded cinematic camera move（已完成）**：在当前镜头包上增加由 Blender 相机预演
  派生的有限三关键帧镜头运动，并在 Unreal Level Sequence 中生成可编辑 Transform Track 与
  起、中、末帧预览。继续复用同一候选和回执语义，不开放任意 Sequencer 脚本或轨道编辑接口。
- **M39 · Live camera-move dispatch（已完成）**：把 Camera Move Request、Blender 动画源、
  派生 Level Sequence 与 Unreal 三帧回执登记为当前 Session 的第十二项生产能力，继续复用
  已有 Worker、事件账本和场景变更谱。
- **M40 · Scene-conditioned material variation set（已完成）**：把 ComfyUI 的节点式视觉条件、
  Blender 的材质节点、UV 与 Bake 能力，以及 Unreal Material Instance / PCG 变体应用组织为
  一条真实表面制作路线。先为现有 Wayfinder 模块生成三组受限色板与粗糙度变体，在可编辑
  `.blend` 中保留节点结构和贴图，再回流隔离候选并按 PCG 变体稳定分配。
- **M41 · Live material-variation dispatch（已完成）**：把 M40 的 ComfyUI 输入、Blender 材质源、
  六张烘焙贴图、三个 Material Instances 与 Unreal PCG 候选登记为当前 Session 的第十三项
  生产能力，复用既有 Worker 和场景变更谱提供直接派发与恢复。
- **M42 · Scene-conditioned terrain and biome blockout（已完成）**：把 Unreal 深度与保护区交给
  固定 ComfyUI 节点子图生成高度场和生物群落分区；Blender 通过可编辑 Geometry Nodes 建立
  场景外围地形、UV 和碰撞代理，Unreal 在隔离候选中接收地形并让项目自有 PCG 图消费分区。
- **M43 · Simulation cache and Sequencer handoff（已完成）**：把 Blender 的确定性模拟与缓存能力
  接入当前 Scene Session；以有限对象集、帧段和预算生成可编辑动画源，再通过 Unreal Geometry
  Cache / Level Sequence 的类型化工具进入派生候选，形成区别于静态建模的时序内容路线。
- **M44 · Live simulation-cache dispatch（已完成）**：把 M43 的地形来源、Blender 动画源、Alembic、
  Geometry Cache、Level Sequence 和候选身份登记为当前 Session 的第十四项有限能力，复用既有
  DCC Worker、append-only 事件链和场景变更谱完成直接派发、恢复与展示。
- **M45 · Biome-driven foliage kit and wind material（已完成）**：复用 M42 生物群落分区，让 Blender
  以曲线与 Geometry Nodes 生成有限植被模块套件，并在 Unreal 中通过项目 PCG 与可调 WPO 风材质
  形成可继续编辑的环境层；三种变体和 18 个实例已在派生候选中完成回流与幂等对账。
- **M46 · Live foliage dispatch（已完成）**：把 M45 的蒙版、点集、Blender 编辑源、三种 GLB/LOD、
  Unreal 风材质、PCG 图和候选身份登记为当前 Session 的第十五项有限能力，接入现有 DCC Worker。
- **M47 · Concept-guided modular environment assembly（进行中）**：把当前 Scene Session 的深度、
  保护区和视觉目标编译为有限模块类别与布局预算，由固定 ComfyUI 空间子图、Blender Geometry
  Nodes 场景装配和 Unreal 类型化 Actor/PCG 消费器共同建立可编辑环境候选。

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
