# M22-S1 · Unreal 原生发布与审阅操作

## 结论

ArtFlow Scene Bridge 1.2.0 已将当前 Scene Session 的发布与精确版本审阅接入 Unreal 中文 Tools 菜单。两个入口调用插件封装的固定 Python 能力，不接受调用方脚本、地图、文件路径或自定义事件结构。

真实 UE 5.8.1 进程完成发布与审阅对账后，当前事件流仍为 37 条，重复外部副作用为 0，源 `ArtFlowDemo.umap` 保存次数为 0。非法自动化动作 `delete` 在运行插件脚本前被拒绝。

| Unreal Published 关卡 | 当前 Scene Session 投影 |
| --- | --- |
| ![Unreal 发布操作打开精确 Published 版本](../../artifacts/goal/m22-s1-unreal-operator/publish-operator-window.png) | ![场景变更谱显示当前版本采用、发布与审阅状态](../../artifacts/goal/m22-s1-unreal-operator/live-operator-spectrum.png) |

## 真实宿主记录

| 操作 | UE 进程 | 结果 |
| --- | ---: | --- |
| 发布当前 ArtFlow 版本 | 46512 | `reconciled`，精确版本 `/Game/ArtFlow/Published/AF_dc31f6ed0f4e/V_6851eebe8a5a` |
| 审阅当前 Published 版本 | 18776 | `reconciled`，12 个 PCG 实例，源关卡保存 0 |
| 非法动作 `delete` | 40708 | 插件脚本运行前拒绝，场景未写入 |

发布和审阅均由新启动的编辑器进程执行。源关卡 SHA-256 为 `620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a`，操作前后保持一致；Published 关卡 SHA-256 为 `a51e21be6b83365a85d00725ae6a237aaaad432f0c2101e270c23625eab0698c`。

## 验证范围

- Unreal Build Tool：`ArtFlowBridgeHostEditor Win64 Development` 编译成功；
- 菜单动作：发布、审阅 2 / 2；
- 幂等重放：事件总数 `37 → 37`；
- 重复外部副作用：0；
- 源关卡写入：0；
- Scene Change Spectrum：1600 × 1000，横向溢出 0、破损图片 0、控制台错误 0；
- 插件封装：发布与审阅脚本均来自 `ArtFlowSceneBridge/Content/Python`。

机器可读汇总位于 [`verification.json`](../../artifacts/goal/m22-s1-unreal-operator/verification.json)，对应日志、回执、宿主运行记录与截图保存在同一目录。
