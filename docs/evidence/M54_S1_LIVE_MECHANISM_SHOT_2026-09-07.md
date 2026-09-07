# M54-S1 · 当前 Session 机关镜头派发

M53 已验证的机关镜头请求、Unreal Level Sequence、派生候选和三张 Sequencer 渲染帧已登记为当前 Scene Session 的第十九项有限能力。派发继续使用既有 append-only 事件账本、确定性 Reducer 和单一 DCC Worker，没有重新运行 Blender、Unreal 或增加第二套调度路径。

## 运行结果

- 工作项：`dcc-work-f04300ec3725`
- 工作身份：`f04300ec372580ab77843dab44ac1f5426cad418feb4bbd8fdcca0453d6d3b05`
- 能力数：19；新增 `unreal.sequencer.mechanism_shot.v1`
- 固定身份：M53 请求、Unreal 回执、候选关卡、Level Sequence 与闭合/开启/闭合三帧哈希均进入工作定义
- 生命周期：`queued → claimed → executing → reconciling → succeeded`，共 5 个 DCC 事件
- 重复派发：返回相同工作身份
- Reducer 重放：恢复状态与终态投影一致
- 重复外部副作用：0
- Level Sequence：`/Game/ArtFlow/Sequences/Generated/LS_AF_MechanismShot_3273ac1a1081.LS_AF_MechanismShot_3273ac1a1081`
- 当前候选：`/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/MechanismShot_B_3273ac1a1081`

## 产品投影

场景变更谱新增“当前 Session · 机关镜头”，直接使用 Unreal Sequencer 渲染的第 1、24、48 帧表达闭合、开启、闭合三态，并公开可追踪的工作身份和回放结果。桌面 1600×1000 与窄屏 980×1200 均无横向溢出，页面媒体加载失败数为 0。

## 证据

- `artifacts/goal/m54-s1-live-mechanism-shot/live-mechanism-shot-work-receipt.json`
- `artifacts/goal/m54-s1-live-mechanism-shot/live-mechanism-shot-desktop.png`
- `artifacts/goal/m54-s1-live-mechanism-shot/live-mechanism-shot-narrow.png`
- `artifacts/goal/m53-s1-mechanism-shot/mechanism-shot-request.json`
- `artifacts/goal/m53-s1-mechanism-shot/unreal-mechanism-shot-receipt.json`
- `artifacts/goal/m53-s1-mechanism-shot/unreal-mechanism-shot-closed_start.png`
- `artifacts/goal/m53-s1-mechanism-shot/unreal-mechanism-shot-open.png`
- `artifacts/goal/m53-s1-mechanism-shot/unreal-mechanism-shot-closed_end.png`
