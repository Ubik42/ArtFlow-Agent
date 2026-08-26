# ArtFlow Agent

> 从 Unreal 场景事实出发，完成受约束生成、独立评价、失败恢复、证据采用、局部纠正与可验证回流的 AIGC 生产 Agent。

ArtFlow 面向游戏美术、技术美术和 AIGC 工具团队。它解决的不是“再做一个 ComfyUI 前端”，而是把相机、物体 ID、保护区域、可编辑区域与美术意图编译成可重放的生产决策链：模型只能在已声明的能力中选择，确定性策略拥有最终约束权，生成器不能评价自己的结果，Codex 编排器依据持久化 Tribunal 证据完成采用、局部修订和项目内交付。

![ArtFlow 最终可验证交付面板](docs/assets/portfolio/09-verified-delivery.png)

## 一次真实闭环

当前作品集主运行使用项目自有 Unreal Engine 5.8 场景和本机 RTX 4080：

```text
Unreal 四 Pass Scene Package
  → 有界 Context + Capability Registry
  → 本地 ComfyUI / Codex 内置 GPT Image 2 同约束候选
  → 确定性 Constraint Judge + 独立多模态 Visual Critic
  → 拒绝“更漂亮但越界”的负对照
  → Codex 编排器从持久证据自主采用
  → GPT Image 2 蒙版限定局部修订
  → 像素级验证蒙版外 0 变化
  → typed Unreal return tool 回写 ArtFlowDemo
  → 9/9 来源文件哈希验证与本地作品集发布
```

这条主运行目前有 **25 个 append-only 事件**，刷新和重启均从 SQLite reducer 重建；没有待处理的人工审批。候选采用、局部修订、UE 回流和最终本地发布由 Codex 编排器负责，预览界面只提供可见性，不会被重新包装成审批门禁。

## 完整流程实录

以下截图均来自同一条项目自有运行，不是概念稿或后期拼接的静态 UI。

| 1. UE 四 Pass 场景事实 | 2. 双 Provider 独立 Tribunal |
| --- | --- |
| ![Unreal 原始场景](docs/assets/portfolio/01-unreal-scene.png) | ![候选 Tribunal](docs/assets/portfolio/02-provider-tribunal.png) |
| 3. 更漂亮但越界的负对照 | 4. 蒙版限定局部纠正 |
| ![负对照硬拒绝](docs/assets/portfolio/03-attractive-invalid.png) | ![有界修订](docs/assets/portfolio/04-bounded-revision.png) |
| 5. 崩溃恢复矩阵 | 6. 来源绑定生产记忆 |
| ![恢复矩阵](docs/assets/portfolio/05-recovery.png) | ![生产记忆](docs/assets/portfolio/06-memory.png) |
| 7. 20/20 Agent Harness | 8. UE 5.8 真实回流 |
| ![Agent Harness](docs/assets/portfolio/07-harness.png) | ![Unreal 回流](docs/assets/portfolio/08-unreal-return.png) |
| 9. 可验证交付总览 | 10. 窄屏展示 |
| ![可验证交付](docs/assets/portfolio/09-verified-delivery.png) | ![移动端交付面板](docs/assets/portfolio/10-mobile-delivery.png) |

## 为什么这是 Agent，而不是工作流脚本

核心工程公式是 `Agent = Model + Harness`。ArtFlow 的主要代码价值位于手写 Harness，而不是某个框架名称：

| Agent 能力 | ArtFlow 实现 | 可检查证据 |
| --- | --- | --- |
| 上下文工程 | 稳定前缀、Reducer 状态栏、最近观察窗口、精确元数据记忆、artifact citation | 深埋硬约束保留；陈旧观察与无关记忆被排除 |
| 工具工程 | Pydantic 输入输出、能力注册、读写域、风险、超时、幂等和独立验证信号 | 不可用能力 fail closed；模型不能提交任意 ComfyUI 图或 host code |
| 路由与策略 | 能力收敛、隐私/成本上限、确定性硬门禁、绑定指纹 | 路由/策略冻结案例 5/5；审批指纹不能绕过 |
| 持久执行 | SQLite append-only 事件、哈希链、确定性 reducer、reserve/submit/reconcile | 崩溃点重放保持相同终态；副作用不重复 |
| 独立评价 | 生产者与 Judge 分离，技术 Tribunal 与多模态 Critic 并列 | 更漂亮但改变相机/结构的负对照被硬拒绝 |
| 纠正 | 失败分类、checkpoint、unknown completion 对账、蒙版限定修订 | 恢复 6/6；局部修订蒙版外变化 0 像素 |
| 生产记忆 | episodic / semantic / procedural 三类来源绑定记忆 | 治理案例 6/6；冲突、伪造来源与越权共享被拒绝 |
| 可观察与评估 | OpenTelemetry 关联 trace；冻结 Harness 聚合六个领域 | 20/20 命名案例，精确分母、fixture 延迟和 $0 外部成本 |
| 可验证交付 | typed UE return receipt、内容哈希、C2PA 2.4 兼容 sidecar | UE 5.8 可见回流；来源绑定 9/9 |

PydanticAI 只负责类型化模型交互，不拥有状态机、策略或执行权限。ArtFlow 没有为了“显得复杂”引入 LangGraph、Temporal、向量数据库或开放式多 Agent 群聊。

## 真实结果与诚实边界

- **Unreal 输入**：UE `5.8.1`，固定相机，beauty / depth / world normal / object ID 四 Pass，Scene Package 原子发布并逐文件 SHA-256。
- **双生成面**：本地 ComfyUI 与 Codex 内置 GPT Image 2 使用同一 Scene Package 和美术约束；输出统一为不可变 receipt。
- **评价分歧**：Codex 候选获得更强视觉方向评价，本地候选保留更强边缘布局代理指标；分歧没有被抹平。
- **负对照**：一个主观吸引力更高的候选因相机和结构违反被确定性硬门禁拒绝，不能进入采用排序。
- **自主采用**：编排器按 `hard-eligible-then-visual-direction-v1` 从已持久化评价选择 Codex 候选。
- **局部纠正**：第二次 feathered composite 改变蒙版内 42,803 个像素，蒙版外 1,530,358 个像素中变化为 0。
- **真实回流**：修订资产导入 `/Game/ArtFlow/Returns`，绑定 `/Game/ArtFlowDemo` 的 `ArtFlow_Return_1194a8d6` Actor，UE 内容验证通过。
- **来源限制**：9/9 文件哈希链通过，但当前是 `compatible_unsigned_sidecar`，没有签名证书，**不声称完整加密 C2PA Credential**。

## 五分钟演示

安装 Python 3.11+ 和 Node.js 后：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
cd web
npm install
npm run build
cd ..
.\.venv\Scripts\python scripts\serve_agent_fixture.py `
  artifacts\goal\m3-s11-local-run --port 8796
```

打开 `http://127.0.0.1:8796`。推荐演示顺序与讲解词见 [演示与复现指南](docs/DEMO_GUIDE.md)。界面读取持久化运行，不会重新调用生成器或消耗 API Token。

## 本地作品集发布

构建只包含声明过的审阅材料，不包含 prompt、事件数据库、凭据或隐藏推理：

```powershell
.\.venv\Scripts\python scripts\build_portfolio_release.py
.\.venv\Scripts\python scripts\verify_portfolio_release.py `
  artifacts\goal\m6-s2-release\artflow-agent-portfolio-<manifest>.zip
```

ZIP 内同时附带仅依赖 Python 标准库的 `tools/verify_release.py`。验证器重新打开发布包，检查所有文件哈希、Run 与事件头、20/20 Harness、6/6 恢复、6/6 记忆和 9/9 unsigned provenance 边界；任何已声明文件被修改都会返回非零退出码。

## 验证

```powershell
.\scripts\goal.ps1 -Action Doctor
.\.venv\Scripts\python -m pytest -q
powershell -ExecutionPolicy Bypass -File scripts\validate.ps1 -Tier quick
```

测试数量是工程回归信号，不替代真实宿主与 artifact 证据。各阶段证据位于 [`docs/evidence/`](docs/evidence/)；稳定完成定义见 [`docs/development/CODEX_GOAL.md`](docs/development/CODEX_GOAL.md)。

## 工程结构

| 路径 | 内容 |
| --- | --- |
| `src/artflow_agent/agent_runtime.py` | append-only 事件、Reducer、幂等状态转换 |
| `src/artflow_agent/agent_harness.py` | Context 装配、能力注册与有界观察 |
| `src/artflow_agent/routing.py` | Provider 路由、隐私/成本策略与指纹 |
| `src/artflow_agent/tribunal.py` | 确定性独立评价与硬门禁 |
| `src/artflow_agent/recovery_eval.py` | 故障注入与 exactly-once 恢复记分卡 |
| `src/artflow_agent/production_memory.py` | 来源绑定生产记忆治理 |
| `src/artflow_agent/provenance.py` | UE return、来源清单与独立验证 |
| `src/artflow_agent/portfolio_release.py` | 确定性发布包与篡改检测 |
| `integrations/unreal/` | 可单独安装的 ArtFlow Scene Bridge 与 UE 5.8 测试宿主 |
| `web/` | React / TypeScript Scene Lab 与证据控制台 |
| `artifacts/goal/` | 当前作品集运行、截图、记分卡与 checkpoint |

`D:\3D\_tools\art-pipeline-skill` 和 `D:\3D\_tools\ComfyUI-Production-Nodes` 是独立 sibling 仓库；前者是可选领域 Skill，后者是版本化 ComfyUI 自定义节点包，都不拥有 ArtFlow 的 Agent 状态。

## 已知限制

- 当前作品集只验证一条项目自有 UE 场景主运行；它是强端到端证据，不是开放域质量 benchmark。
- 20/20 Harness 延迟是本地冻结夹具延迟，不代表真实 provider 生产延迟。
- C2PA sidecar 使用 2.4 断言词汇并可验证内容哈希，但没有 JUMBF 嵌入、证书或签名。
- 发布包刻意不携带 prompt 与 SQLite 数据库；完整事件重放在开发仓内完成，发布包提供事件头和经过清洗的证据摘要。
- 项目当前面向 Windows、UE 5.8、ComfyUI 本机工作流；未声称验证其他平台和 Unreal 版本。
