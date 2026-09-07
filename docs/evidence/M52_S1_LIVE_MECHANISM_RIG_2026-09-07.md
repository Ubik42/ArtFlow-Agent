# M52-S1 · 当前 Session 机关动画派发

M51 已验证的机关请求、Blender 编辑源、FBX、骨骼/动作清单和 Unreal 候选已登记为当前 Scene Session 的第十八项有限 DCC 能力。派发继续使用既有 append-only 事件账本、确定性 Reducer 和单一 Worker，没有启动新的 Blender/Unreal 进程或增加并行状态机。

## 运行结果

- 工作项：`dcc-work-3d35c2e9e26d`
- 能力数：18；新增 `blender.armature.articulated_gate.v1`
- 固定身份：请求、Blender 回执、Manifest、FBX、Unreal 回执和候选关卡均进入工作定义
- 生命周期：`queued → claimed → executing → reconciling → succeeded`，共 5 个 DCC 事件
- 重复派发：返回相同工作身份
- Reducer 重放：恢复状态与终态投影一致
- 重复外部副作用：0
- 当前候选：`/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Mechanism_B_2762b53baeec`

## 产品投影

场景变更谱新增“当前 Session · 机关动画”，使用三段真实媒体表达视觉目标、Blender 绑定动作和 Unreal 动画资产。桌面 1600×1000 与窄屏 980×1200 均无横向溢出；三张媒体加载成功；浏览器控制台错误和警告均为 0。

## 证据

- `artifacts/goal/m52-s1-live-mechanism-rig/live-mechanism-rig-work-receipt.json`
- `artifacts/goal/m52-s1-live-mechanism-rig/live-mechanism-rig-desktop.png`
- `artifacts/goal/m52-s1-live-mechanism-rig/live-mechanism-rig-narrow.png`
- `artifacts/goal/m51-s1-mechanism-rig/mechanism-rig-request.json`
- `artifacts/goal/m51-s1-mechanism-rig/blender-mechanism-rig-receipt.json`
- `artifacts/goal/m51-s1-mechanism-rig/unreal-mechanism-rig-receipt.json`
