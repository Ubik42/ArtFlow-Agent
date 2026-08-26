# ArtFlow Agent 演示与复现指南

## 用途

这份指南用于作品集面试、技术演示和代码审阅。演示读取已经完成且有内容哈希的主运行，不重新运行 ComfyUI、GPT Image 或 Unreal，避免网络、GPU 和模型波动破坏叙事。

## 启动

```powershell
cd D:\3D\_tools\ArtFlow-Agent
.\.venv\Scripts\python scripts\serve_agent_fixture.py `
  artifacts\goal\m3-s11-local-run --port 8796
```

打开 `http://127.0.0.1:8796`。预期看到 `ArtFlowDemo`，事件序列为 25，没有待处理决策。

## 五分钟黄金路径

### 0:00–0:40：真实输入，不是 prompt demo

- 指向 UE 5.8 来源、640×360 相机、四个 Pass。
- 展开 protected / editable 区域，说明模型不能任意修改场景。

### 0:40–1:30：同源候选与能力路由

- 对比本地 ComfyUI 和 Codex Image 候选。
- 说明本地路线先经过真实节点、模型和 RTX 4080 attestation；两路 receipt 绑定同一个 Scene Package 与 art intent hash。

### 1:30–2:20：独立 Tribunal 与负对照

- 展示 deterministic claims 与多模态视觉评价。
- 切到 attractive-invalid control：视觉更吸引人，但改变相机/结构，因硬门禁被拒绝。
- Visual Critic 不能覆盖 deterministic failure，分歧被保留。

### 2:20–3:05：自主采用与局部纠正

- 展示 `codex-orchestrator` 按 `hard-eligible-then-visual-direction-v1` 采用合格候选。
- 拖动 before/after；展示 mask、父图和 composite hash。
- 蒙版外 1,530,358 像素中变化为 0，蒙版内 42,803 像素变化。

### 3:05–4:10：证明 Harness

- Recovery 6/6，五个副作用场景重复次数 0。
- episodic / semantic / procedural 三类生产记忆，治理 6/6。
- Frozen Harness 20/20；Context 3/3、路由/策略 5/5、误打断 0/1、重复副作用 0/5、外部 fixture 成本 $0。
- 主动说明延迟是本地 fixture，不是 provider SLA；20/20 不代表开放域生图质量。

### 4:10–5:00：回到 Unreal

- 展示绿色交付面板：真实 UE 视口、目标关卡、引擎版本、事件序列与 delivery identity。
- 来源绑定 9/9 通过；验证器独立于前端。
- 主动指出当前是 unsigned C2PA sidecar，没有签名证书。

## 失败路径复现

```powershell
.\.venv\Scripts\python scripts\run_recovery_matrix.py
```

预期 `6/6`、`duplicate_side_effect_count=0`。每个案例使用独立 fixture 和 trace，不修改主运行。

## 发布包验证

```powershell
.\.venv\Scripts\python scripts\build_portfolio_release.py
.\.venv\Scripts\python scripts\verify_portfolio_release.py `
  artifacts\goal\m6-s2-release\artflow-agent-portfolio-<manifest>.zip
```

也可解压 ZIP 使用包内 `tools/verify_release.py`，它只依赖 Python 标准库。修改任何已声明文件后应得到 `file_hash_mismatch:*` 和非零退出码。

## 演示中的禁语

- 不说“完整 C2PA 已签名”；只能说“C2PA 2.4 vocabulary-compatible unsigned sidecar，哈希链可验证”。
- 不把 20/20 说成通用模型准确率；它是 20 个命名冻结案例。
- 不说“人工采用率 100%”；当前采用由 Codex 编排器依据一次真实项目 Tribunal 证据完成。
- 不把 fixture latency 说成 ComfyUI 或 GPT Image 生产延迟。
- 不展示 prompt、密钥、隐藏推理或 SQLite 原始内容。

## 录屏前检查

- 浏览器宽度 1440，缩放 100%。
- 先运行 `npm run build`，再启动 fixture server。
- 所有图片加载完成、控制台 0 error / 0 warning、页面无横向滚动。
- 主运行事件数为 25，最终交付面板显示 9/9 和 unsigned C2PA 限制。
- 演示结束后关闭本地 fixture server；不需要登录外部账户。
