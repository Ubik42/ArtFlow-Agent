# M12-S1 Unreal 原生 Scene Session 握手

## 交付结果

Unreal 编辑器现可直接发起 ArtFlow 场景任务。插件从当前已保存关卡导出带内容哈希的 Scene
Package，只向显式 `127.0.0.1` 或 `localhost` 端口提交原始 ZIP；本地 Agent 在同一个请求内完成
场景导入、Scene Session 启动和候选请求编译，再返回
`artflow-scene-session-handshake/1` 回执。

UE 在接受回执前核对源关卡、Scene Package、run、Session、draft、策略版本和候选目录。候选目录
必须位于 `/Game/ArtFlow/Sessions/`，源 `.umap` 的前后 SHA-256 必须相同。通过后，宿主回执写入
项目自己的 `Saved/ArtFlowSceneBridge/SceneSessions`。

本切片只建立任务和候选请求，没有执行请求中的 image、asset、PCG 或 lighting 操作，也没有创建、
保存或发布候选关卡。

## 真实 UE 5.8 运行

测试宿主：项目自有 `ArtFlowBridgeHost`，Unreal Engine `5.8.1`。

```text
插件编译：Succeeded
源关卡：/Game/ArtFlowDemo
Scene Package：1d00b61e385de0cbc842a7be8999e59cabeb87f75bf0b87df83269eba812914a
Session：e5857bc3d1238eb969e884c9d23694c2ba2b0b1be81550453a2c9344e1a7b15a
Stage Request：a9df851fc1f26d2b5c8e563c85145137bbd10f7a160e826b6334a2be35645c63
候选目录：/Game/ArtFlow/Sessions/AF_e5857bc3d123/Candidates/C_a9df851fc1f2
源关卡 SHA-256（前/后）：620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a
```

对同一真实 ZIP、动作标识和元数据再次提交后，时间线仍为 3 个事件，其中
`scene_session_started` 为 1 个；重复 Session 事件为 0。

## 聚焦验证

```text
.venv\Scripts\python.exe -m pytest tests/test_web_api.py -q
11 passed

.venv\Scripts\python.exe -m ruff check <changed Python files>
All checks passed

UnrealBuildTool ArtFlowBridgeHostEditor Win64 Development
Result: Succeeded

Real UE handshake
ARTFLOW_SESSION_HANDSHAKE_RESULT success=true source_unchanged=true
```

## 证据

- `artifacts/goal/m12-s1-live-handshake/unreal-session-handshake-receipt.json`
- `artifacts/goal/m12-s1-live-handshake/unreal-session-handshake-proof.log`
- `artifacts/goal/m12-s1-live-handshake/replay-summary.json`
- `artifacts/goal/m12-s1-live-handshake/unreal-editor-scene-session-cn.png`

## 证据上限

证据证明真实 Unreal 编辑器能够从源关卡发起 localhost-only Scene Session，验证回执身份、保存
回执并保持源关卡字节不变；也证明相同网络请求的重放不会新增 Session 事件。它不证明候选操作已经
执行，不证明生成质量，也不证明候选关卡已经发布。
