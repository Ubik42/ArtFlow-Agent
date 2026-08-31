# ArtFlow Agent

面向 Unreal Engine 美术生产的场景智能体。ArtFlow 将二维视觉意图转化为可审查、可回滚、可追溯的材质、资产、PCG 与灯光变更，并在隔离候选关卡中完成执行、评价、纠正和发布。

![ArtFlow 场景变更谱与候选关卡请求](artifacts/goal/m11-s2-persistent-session-stage-request.png)

## 项目定位

游戏美术团队已经能够使用 ComfyUI、图像模型和各类生成服务快速产出概念方案，但把生成结果真正带入 Unreal 生产管线仍有明显断层：

- 生成模型不了解关卡中的相机、保护对象、空间边界和现有资产；
- 图片、材质、模型、PCG 与灯光分别存在于不同工具，缺少统一的变更计划；
- 候选结果通常依赖主观选择，难以解释为什么采用、为什么拒绝；
- 超时或进程中断后盲目重试，可能造成重复生成、重复导入和脏资产；
- 二维参考图很难直接落实为引擎内可编辑、可复检的三维结果。

ArtFlow 在生成模型与 Unreal 之间增加一层受约束的 Agent 控制平面。它读取真实场景事实，将目标编译为类型化 `SceneChangePlan`，只调用经过声明的有限工具，并以独立评价和确定性规则决定后续动作。所有场景写入首先发生在候选关卡，源关卡不会被直接覆盖。

### 从当前 Unreal 场景开始

使用者可直接从 Unreal 编辑器的“启动 ArtFlow 场景任务”进入，也可以在“场景变更谱”中描述本轮美术意图。编辑器入口会导出当前已保存关卡，向仅监听 localhost 的 Agent 发起类型化握手，并在确认 Scene Package、Session、策略与候选目录身份后把回执留在项目 `Saved` 目录。整个握手不修改源关卡。

视觉参考、材质、三维资产、空间布局和灯光是可独立编排的变更领域。ArtFlow 根据 Scene Digital Twin 与实际运行时能力标出可执行、待补齐和实验路线；确认后的 Scene Session 进入 append-only 账本，刷新或重启不会丢失。

当所有选定领域满足前置条件时，系统生成一份与场景哈希、Session、策略版本和领域操作严格绑定的候选关卡请求。请求只能指向 ArtFlow 派生的隔离内容目录；截图中的状态表示“请求已封存”，不表示 Unreal 已经完成本次写入。

## 生产案例

Scene Lab 使用同一套 Agent 控制平面呈现四类典型任务。界面中的状态、指标和结果均来自实际运行回执。

| 概念道具生成与接入 | PBR 材质生成与回流 |
| --- | --- |
| ![GPT Image 2 参考生成 GLB 并接入 Unreal](docs/assets/showcase/scene-lab-image-to-3d.png) | ![ComfyUI PBR 材质验证与回流](docs/assets/showcase/scene-lab-pbr.png) |
| 场景多域联合改造 | 失败域定向纠正 |
| ![材质、PCG、灯光与项目资产联合改造](docs/assets/showcase/scene-lab-multi-domain.png) | ![评价失败后仅纠正灯光](docs/assets/showcase/scene-lab-correction.png) |

### 概念道具生成与接入

二维概念参考经过图生 3D Provider 生成 GLB。资产进入引擎前必须通过许可证、外部 URI、格式扩展、几何规模、材质表示和三角面预算检查；合格结果再由 Unreal Interchange 导入隔离命名空间，创建碰撞并放入候选关卡。

| 二维概念参考 | Unreal 三维候选 |
| --- | --- |
| ![玄武岩祭坛概念参考](docs/assets/showcase/image-to-3d-reference.png) | ![Unreal 中的生成祭坛候选](docs/assets/showcase/image-to-3d-unreal.png) |

本次结果在 Unreal 中构建为 4,817 个三角面、1 个材质槽和 1 个简单碰撞，并以约 180 cm 的尺度进入候选关卡。当前路线定位为实验性几何草案，保留顶点色，不将其描述为最终生产级 PBR 资产。

### PBR 材质生成与回流

ArtFlow 只允许视觉意图、种子、尺寸和输出前缀进入受审 ComfyUI 模板，不接受任意工作流执行。生成后的 BaseColor、Normal、Roughness、Metallic 与 AO 分别进行尺寸、通道语义和内容哈希检查；失败通道单独重建，通过后创建 Unreal Material Instance 并等待 Shader 编译完成再回渲。

| 通过验证的 BaseColor | Unreal 同机位回渲 |
| --- | --- |
| ![玄武岩 BaseColor](docs/assets/showcase/pbr-basecolor.png) | ![Unreal 材质候选回渲](docs/assets/showcase/pbr-unreal.png) |

两组无效结果因彩色标量图、法线语义错误等问题被拦截；最终五个通道全部通过，重复执行没有新增资产，源关卡保持不变。

### 场景多域联合改造

Agent 将项目资产、已验证材质、固定 PCG 图和灯光参数编译为带依赖关系的变更 DAG。非引擎资产可以并行准备，Unreal 写入严格串行。候选完成后同时从美术机位和瞬态验证机位回渲，检查镜头外遮挡、保护区侵入与实例空间关系。

| 美术机位 | 空间验证机位 |
| --- | --- |
| ![场景改造主机位](docs/assets/showcase/multi-domain-authored.png) | ![场景改造验证机位](docs/assets/showcase/multi-domain-validation.png) |

真实运行生成 12 个 PCG 实例，保护区侵入为 0；重复执行仍保持 12 个实例和相同的资产集合。

### 失败域定向纠正

评价器分别检查技术约束与视觉目标。当一次低照度候选只在 `lighting` 域失败时，Correction Planner 锁定已经通过的资产、材质与 PCG 证据，只生成灯光补丁，不重新调用生成或导入链路。

| 失败回渲：平均亮度 117.72 | 纠正回渲：平均亮度 166.66 |
| --- | --- |
| ![灯光失败回渲](docs/assets/showcase/correction-before.png) | ![灯光纠正回渲](docs/assets/showcase/correction-after.png) |

纠正过程中注入回执丢失，恢复进程通过持久账本对账已有结果，外部重提次数为 0；重复发布同样不会产生额外副作用。

## 工作流程

![ArtFlow 使用流程](docs/assets/portfolio/11-agentic-workflow-comic.png)

1. **场景理解**：Unreal Bridge 导出 Beauty、Depth、World Normal、Object ID，以及相机、Actor、材质、灯光、PCG、保护对象和空间边界。
2. **计划编译**：Agent 把美术目标编译为类型化 Scene Delta DAG，并根据隐私、成本、宿主能力与风险选择可用工具。
3. **候选执行**：ComfyUI、GPT Image 2、图生 3D Provider 和 Unreal 工具只执行各自声明范围内的任务，不拥有最终决策权。
4. **独立评价**：确定性 Constraint Judge 优先检查硬约束，多模态 Visual Critic 评价视觉方向；视觉吸引力不能覆盖相机、结构或保护区失败。
5. **纠正与发布**：只重跑失败领域，通过复检的候选以内容寻址方式发布；失败候选可以丢弃，源关卡始终保持不变。

## 系统架构

![ArtFlow 系统架构](docs/assets/portfolio/12-agent-architecture-comic.png)

```text
Unreal Scene Bridge
        │
        ▼
Scene Digital Twin ── Context Assembler ── Production Memory
        │
        ▼
Planner / Capability Router / Policy Engine
        │
        ├── ComfyUI PBR
        ├── GPT Image 2
        ├── Image-to-3D Provider
        └── Typed Unreal Tools
        │
        ▼
Candidate Level ── Technical Judge ── Visual Critic
        │
        ▼
Correction Planner ── Reconcile ── Publish / Discard
        │
        ▼
SQLite Event Log / Provenance / OpenTelemetry
```

MCP 作为薄互操作层，只投影已经存在的固定资源与窄工具。它不接收任意本地路径、ComfyUI workflow、Python、Shell 或 Blueprint，也不维护第二套 Agent 状态机。

## Agent 工程设计

| 能力 | 实现方式 | 生产约束 |
| --- | --- | --- |
| 上下文工程 | Scene Digital Twin、稳定约束前缀、最近观察、来源绑定记忆 | 陈旧观察与无关项目记忆不会进入当前决策 |
| 工具系统 | Pydantic 输入输出、能力注册、读写域、风险、超时与验证信号 | 不暴露任意主机代码或任意 ComfyUI 图 |
| 路由与策略 | 能力实测、隐私/成本上限、内容指纹、确定性硬门禁 | 模型置信度不能覆盖规则失败 |
| 持久执行 | SQLite append-only 事件、确定性 Reducer、`reserve / submit / reconcile` | 超时被视为“结果未知”，不会直接重提 |
| 独立评价 | 生成器、Technical Judge 与 Visual Critic 权限分离 | 生成器不能评价或采用自己的结果 |
| 定向纠正 | 失败域分类、检查点与已通过证据锁定 | 一处失败不会触发整条生成链重跑 |
| 生产记忆 | episodic / semantic / procedural 记录与来源引用 | 冲突、伪造来源和越权共享会被拒绝 |
| 可验证交付 | 类型化 Unreal 回执、内容哈希、来源 sidecar | 所有公开结论均可回到实际制品与分母 |

PydanticAI 仅用于类型化模型边界；状态机、工具权限、策略、恢复、评价和发布逻辑均由项目自身实现。系统没有为了增加概念数量而引入开放式多 Agent 协作、向量数据库或第二套工作流引擎。

## 验证结果

| 验证项 | 结果 |
| --- | ---: |
| Agent Harness 冻结案例 | 20 / 20 |
| 崩溃恢复场景 | 6 / 6 |
| 恢复测试中的重复外部副作用 | 0 |
| 生产记忆治理案例 | 6 / 6 |
| PBR 通道验证 | 5 / 5 |
| 多域 Scene Delta | 4 / 4 |
| PCG 保护区侵入 | 0 / 12 |
| 定向纠正重跑范围 | 仅 lighting，1 / 4 |
| MCP 越权输入拦截 | 4 / 4 |
| 来源文件哈希绑定 | 9 / 9 |
| 发布包内容寻址验证 | 36 / 36 |
| Scene Lab 浏览器检查 | 0 溢出、0 控制台错误、0 阻塞弹窗 |
| Scene Session 重复启动 | 1 个持久事件、0 个重复事件 |
| 陈旧候选请求拦截 | 1 / 1 |
| UE 原生 Scene Session 握手 | 1 次真实 UE 5.8 运行，源关卡哈希不变 |
| 同一真实握手请求重放 | 1 个 Session 事件、0 个重复事件 |

这些数据描述仓库内固定场景和命名测试集，不代表开放域生成质量或商业 Provider 的服务等级。详细运行记录见 [验证证据目录](docs/evidence/)。

## 运行环境

- Windows
- Unreal Engine `5.8.1`
- Python `3.11+`
- Node.js 与 npm
- 本地生成验证设备：NVIDIA GeForce RTX 4080 16 GB
- ComfyUI 自定义节点：独立维护的 `ComfyUI-Production-Nodes`

其他平台与 Unreal 版本尚未完成同等级验证。

## 本地演示

```powershell
git clone https://github.com/Ubik42/ArtFlow-Agent.git
cd ArtFlow-Agent

python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"

cd web
npm install
npm run build
cd ..

.\.venv\Scripts\python scripts\run_showcase.py --port 8796
```

浏览器打开 `http://127.0.0.1:8796`。演示读取已经完成且经过哈希绑定的运行，不会重新调用图像或三维生成服务。推荐讲解顺序见 [演示与复现指南](docs/DEMO_GUIDE.md)。

Unreal Bridge 的安装与宿主入口见 [Unreal 集成说明](integrations/unreal/README.md)。

## MCP 互操作

启动本地 stdio Server：

```powershell
uv run python scripts/run_artflow_mcp.py
```

边界验证会读取固定资源、调用全部窄工具，并确认路径注入、任意工作流和任意代码执行全部失败关闭：

```powershell
uv run python -m pytest tests/test_mcp_facade.py -q
```

## 可验证发布

```powershell
.\.venv\Scripts\python scripts\build_portfolio_release.py
.\.venv\Scripts\python scripts\verify_portfolio_release.py <生成的 ZIP 路径>
```

发布包只包含声明过的文档、截图和证据摘要，不包含提示词、凭据、隐藏推理或事件数据库。ZIP 内附带仅依赖 Python 标准库的独立验证器；修改任何已声明文件都会导致验证失败。

## 代码结构

| 路径 | 职责 |
| --- | --- |
| `src/artflow_agent/agent_runtime.py` | 持久事件、Reducer 与幂等状态转换 |
| `src/artflow_agent/agent_harness.py` | 上下文装配、能力注册与有界观察 |
| `src/artflow_agent/contracts/scene_delta.py` | Scene Digital Twin 与类型化 Scene Delta |
| `src/artflow_agent/routing.py` | Provider 路由、隐私/成本策略与指纹 |
| `src/artflow_agent/tribunal.py` | 独立评价与确定性硬门禁 |
| `src/artflow_agent/scene_lifecycle.py` | 多域执行、纠正、恢复与发布 |
| `src/artflow_agent/scene_session.py` | Scene Session 草案、持久身份与候选关卡请求 |
| `src/artflow_agent/pbr.py` | PBR 合同、通道验证与受审图编译 |
| `src/artflow_agent/image_to_3d.py` | 图生 3D 合同、GLB 预检与 UE 接纳 |
| `src/artflow_agent/mcp_facade.py` | 内容寻址 MCP 薄适配层 |
| `src/artflow_agent/provenance.py` | Unreal 回执、来源清单与验证 |
| `integrations/unreal/` | Unreal Scene Bridge 与 UE 测试宿主 |
| `web/` | React / TypeScript Scene Lab |

## 已知限制

- 当前实机证据来自一套项目自有 Unreal 演示场景，不将其包装为开放域质量基准。
- 图生 3D 路线当前用于几何草案验证，尚未覆盖高质量拓扑、UV、最终 PBR 和角色资产。
- PBR 路线使用固定受审 ComfyUI 模板，不提供任意节点图执行。
- C2PA sidecar 使用 2.4 断言词汇并验证内容哈希，但尚未嵌入 JUMBF，也没有证书签名。
- 当前支持 Windows、Unreal 5.8 与本地 ComfyUI 工作流，其他宿主组合仍需单独验证。

## 文档

- [产品与能力边界](docs/PRODUCT_VISION_2026.md)
- [Unreal AIGC 场景转换调研](docs/research/UNREAL_AIGC_SCENE_TRANSFORMATION_2026-08-27.md)
- [演示与复现指南](docs/DEMO_GUIDE.md)
- [完整验证证据](docs/evidence/)
