# Unreal 集成

`ArtFlowSceneBridge/` 是可安装到 Unreal Engine 项目的 Editor 插件；
`ArtFlowBridgeHost/` 是仓库内随附的 UE 5.8 示例项目，用于复现截图、回执和自动化案例。
Bridge 的能力不依赖这个示例项目，实际项目可以使用相同入口导出自己的关卡。

## 安装

将 `ArtFlowSceneBridge` 放入目标项目的 `Plugins` 目录，或像示例宿主一样通过
`AdditionalPluginDirectories` 引用插件目录，然后重新生成项目文件并编译 Editor Target。
插件只在编辑器中运行，不修改 Engine 安装目录。

## 从 Unreal 发起场景任务

1. 保存当前关卡；
2. 选中且仅选中一个 `CameraActor`；
3. 给需要保持不变的 Actor 添加 `ArtFlow.Protected` Tag，给允许进入候选方案的 Actor 添加
   `ArtFlow.Editable` Tag，并把两类 Actor 一同选中；
4. 启动本地 ArtFlow 服务：

   ```powershell
   uv run python scripts\serve_agent_fixture.py runs --port 8798
   ```

5. 在 Unreal 顶部菜单选择 `Tools > ArtFlow > 启动 ArtFlow 场景任务`。

如项目配置仍使用其他端口，可在启动编辑器时追加
`-ArtFlowEndpoint=http://127.0.0.1:8798`。插件会完成 Scene Package 导出、localhost 握手、
Scene Session 建立和候选请求验证。成功回执保存到：

```text
<Project>/Saved/ArtFlowSceneBridge/SceneSessions/
```

该动作不弹出权限确认，也不修改或保存源关卡。当前编辑器菜单先建立候选请求；Agent 后续可将
本次已经就绪的 PCG 与灯光域编译为 Candidate Plan，在请求派生的候选关卡中执行并保存回执。
候选执行仍不等于发布，源关卡不会被覆盖。

作品集只读演示无需启动 Unreal，直接在仓库根目录运行 `scripts\start_showcase.ps1`。它读取冻结
回执，不会把演示点击写回 UE 项目，也不需要任何账户登录态。

## 审阅已发布场景版本

`review_published_variant.py` 是固定的 Published 版本审阅入口。它读取
`artflow-scene-variant-review-request/1`，要求编辑器当前打开的关卡、磁盘关卡哈希、采用决定和
技术事实全部一致，然后输出 `artflow-scene-variant-review-receipt/1`。重复审阅会从项目 Saved
目录对账，但仍重新检查当前关卡；脚本不保存源关卡，也不接受任意包路径或任意 Python 内容。

## 配置

项目配置位于 `Config/ArtFlowSceneBridge.json`：

| 字段 | 含义 |
| --- | --- |
| `width` / `height` | Beauty、Depth、World Normal、Object ID 的导出尺寸 |
| `goal` | 本轮场景意图 |
| `artflow_endpoint` | ArtFlow 本地服务 Origin，只接受带明确端口的 `127.0.0.1` 或 `localhost` |
| `session_domains` | 本轮允许编排的 `image`、`material`、`asset`、`pcg`、`lighting` 领域 |
| `preserve` | 必须保持的场景关系 |
| `prohibit` | 明确禁止的变化 |

命令行实测可用 `-ArtFlowEndpoint=http://127.0.0.1:<port>` 临时覆盖端口。非回环地址、URL
路径、查询参数、未知领域、重复领域和越出 `/Game/ArtFlow/Sessions/` 的候选目录都会在任何场景
写入前失败关闭。

## 示例宿主与证据

`ArtFlowBridgeHost` 保存 `ArtFlowDemo`、PCG 图和用于真实宿主验证的项目资产。`Binaries`、
`Intermediate`、`Saved` 与 `DerivedDataCache` 是本地运行产物；公开证据会复制到
`artifacts/goal/`，并明确区分“请求已建立”“候选已执行”和“结果已发布”。
