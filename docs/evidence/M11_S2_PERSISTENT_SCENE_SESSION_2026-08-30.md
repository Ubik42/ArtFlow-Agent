# M11-S2 持久 Scene Session 与候选关卡请求

## 交付结果

Scene Session 现已进入 ArtFlow 自己的 append-only 事件控制平面。用户在场景变更谱中确认意图和
领域后，后端重新从当前 reducer 状态编译草案、核对草案身份并追加 `scene_session_started`。同一
`action_id` 重放返回原 Session，不新增事件；新进程可以从 SQLite 完整恢复意图、领域、就绪度、
策略和场景身份。

已持久化且没有 guarded 领域的 Session 可以生成 `artflow-scene-stage-request/1`。该请求绑定：

- Agent run、Scene Package SHA-256 与源关卡；
- Session、draft SHA-256 和 `scene-session-strategy/1`；
- 有序领域操作、依赖和验证信号；
- `scene-stage:<request_sha256>` 幂等键；
- `/Game/ArtFlow/Sessions/AF_<session>/Candidates/C_<request>` 隔离内容目录。

请求是即将交给 Unreal 的执行输入，不是完成回执。本切片没有调用 Provider，也没有修改 Unreal。

## 状态与失效规则

- 草案新增 `basis_sequence`，从编译到启动之间若事件账本变化，旧草案必须重新编译；
- 相同启动动作绑定不同输入会失败关闭；
- stage request 只能从最新持久 Session 生成，陈旧 draft hash 以 HTTP 409 拒绝；
- stage request 为纯函数，同一 Session 重复生成身份相同且不追加事件；
- guarded 领域不能进入候选执行，experimental 领域仍需后续 Unreal 接纳检查。

## 聚焦验证

```text
.venv\Scripts\python.exe -m pytest tests/test_web_api.py -q
10 passed

.venv\Scripts\python.exe -m ruff check <changed Python files>
All checks passed

npm run build
TypeScript + Vite production build passed

Playwright 1920x1080 focused flow
启动场景任务 → 生成候选请求 · 0 console errors · 0 warnings
```

截图：`artifacts/goal/m11-s2-persistent-session-stage-request.png`。

## 证据上限

证据证明 Session 的 exactly-once 启动、重启恢复、陈旧身份拒绝和候选请求编译。截图中的“请求已
封存”不表示 Unreal 已执行。编辑器发起握手、候选关卡写入和宿主回执从 M12 开始验证。
