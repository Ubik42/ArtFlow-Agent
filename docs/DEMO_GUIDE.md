# ArtFlow Agent 演示与复现指南

## 快速启动

在仓库根目录运行：

```powershell
.\scripts\start_showcase.ps1
```

脚本会构建当前前端，在本机 `127.0.0.1:8798` 启动只读展示，并在服务就绪后打开浏览器。它读取
已经冻结且经过内容哈希绑定的 UE 5.8、ComfyUI 与 Codex Image 运行，不重新调用生成服务，不需要
登录态，也不会写入 Unreal 源关卡。使用 `-NoBrowser` 可只启动服务。

## 五分钟展示路线

### 0:00–0:45：产品问题

从 README 首图或 Scene Lab 的“场景变更谱”开始。ArtFlow 解决的不是再做一个生图界面，而是把
二维视觉意图落实为 Unreal 内可编辑、可复检的材质、资产、PCG 和灯光变更。模型只能调用注册过
的有限工具，所有写入先进入隔离候选关卡。

### 0:45–2:00：雨后庭院全管线

选择“雨后庭院 · 全管线”。源机位的相机、灰盒和保护区先被锁定；Agent 再把 ComfyUI PBR、
项目资产、固定 PCG 图和灯光编译成同一份 Candidate Plan。指出界面中的 `12` 个实例、`0` 次源
关卡改写，以及新 UE 进程对账时没有重复调用 Provider 或重新导入。

### 2:00–3:20：晴光庭院定向纠正

选择“晴光庭院 · 定向纠正”。依次展示三个镜头：GPT Image 2 视觉目标、故意注入错误主光的 UE
候选、只修正灯光后的 UE 候选。评价器只返回 `lighting` 失败；图像、材质、资产与 PCG 四个成功
域的证据哈希被锁定，Correction Planner 只下发 `unreal.lighting.rig.patch`。

实测主光由 `0.05 / 6500K` 改为 `5.5 / 4200K`，12 个 PCG 实例、材质路径、项目资产集合和保护
对象状态均未变化。修正后的 UE 新进程返回 `reconciled=true`，外部重复提交为 0。

### 3:20–4:10：Agent 工程能力

沿能力轨道说明五个工程要点：

1. Scene Digital Twin 将相机、Actor、材质、灯光、PCG、边界和保护对象变成可引用事实；
2. Planner 生成带依赖和内容身份的类型化 Scene Delta，而不是自由编写宿主脚本；
3. Capability Router 在 GPT Image、ComfyUI、项目资产与 Unreal 工具之间选择真实可用路线；
4. Technical Judge 与 Visual Critic 独立于生成器，硬约束不能被模型自评分覆盖；
5. append-only 事件、reserve / submit / reconcile 和失败域纠正避免重复生成与重复导入。

### 4:10–5:00：回到 Unreal 与证据

展示 `Tools > ArtFlow > 启动 ArtFlow 场景任务`：插件导出当前已保存关卡并向 localhost Agent 发起
握手，回执进入项目 `Saved/ArtFlowSceneBridge/SceneSessions/`。强调“候选已执行”不等于“已发布”；
当前两个 M13 案例都停在隔离候选，没有覆盖源 `ArtFlowDemo.umap`。

最后打开 `docs/evidence/M13_S1_RAIN_WET_CROSS_PIPELINE_2026-08-30.md` 与
`docs/evidence/M13_S2_SUNLIT_IMAGE_ROUTE_CORRECTION_2026-08-30.md`，说明 README 数字都能定位到
计划、回执、固定分母和真实截图。

## Unreal 实际入口

若要从示例宿主真实发起新 Session：

```powershell
uv run python scripts\serve_agent_fixture.py runs --port 8798
```

保存关卡，选中一个 CameraActor 和带 `ArtFlow.Protected` / `ArtFlow.Editable` Tag 的 Actor，然后在
Unreal 菜单选择 `Tools > ArtFlow > 启动 ArtFlow 场景任务`。完整配置和边界见
[`integrations/unreal/README.md`](../integrations/unreal/README.md)。

## 发布包验证

```powershell
uv run python scripts\build_portfolio_release.py
uv run python scripts\verify_portfolio_release.py `
  artifacts\goal\m14-s1-release\artflow-agent-portfolio-<manifest>.zip
```

也可解压 ZIP 使用包内 `tools/verify_release.py`。验证器只依赖 Python 标准库；任何已声明文件被
修改都会返回非零退出码。发布包不包含 prompt、凭据、SQLite 事件数据库、隐藏推理或候选运行时。

## 录屏前检查

- 桌面使用 1920×1080；另检查 760×1080 窄屏；
- 两个案例均能切换，所有图片加载完成；
- 控制台 0 error / 0 warning，无权限弹窗和阻塞遮罩；
- 不把固定场景的 5/5、12 个实例或 Harness 20/20 描述为开放域模型准确率；
- 不声称候选已发布，不展示 prompt、密钥、SQLite 原始内容或本机私有路径。
