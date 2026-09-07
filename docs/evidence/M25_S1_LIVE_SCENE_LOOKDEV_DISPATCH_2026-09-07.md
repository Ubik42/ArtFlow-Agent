# M25-S1 · Live scene-conditioned lookdev dispatch

M24 验证的 ComfyUI → Blender → Unreal Lookdev 已接入当前 Scene Session 的 DCC Worker 和场景变更谱。

![当前 Scene Session 的三段 Lookdev 路线](../../artifacts/goal/m25-s1-live-lookdev/live-lookdev-route.png)

## 产品路径

1. `scene-dcc-work/queue` 从当前 Session 和冻结回执编译唯一工作身份；接口不接收命令、路径或节点图。
2. 本地 Worker 原子领取工作项并依次写入 `claimed / executing / reconciling / succeeded`。
3. Worker 重新验证 ComfyUI 视觉目标、Blender `.blend`/预演和 Unreal 截图的内容身份，将 M24 Unreal 回执作为最终 outcome。
4. React 场景变更谱从同一 projection 显示三段媒体、能力范围、最终候选与对账结果。

## 固定结果

| 项目 | 结果 |
| --- | --- |
| Work | `dcc-work-a3f7ad1e4374` |
| 登记能力 | 建模 / ComfyUI PBR / Geometry Nodes / 镜头灯光 / Scene Lookdev，5 / 5 |
| DCC 生命周期事件 | 5 个 |
| 最终候选 | `/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Lookdev_B_4a01b62f9d58` |
| 最终 outcome | M24 Unreal Lookdev receipt `7d692272…dde2e8f` |
| 重复派发 | 相同 work identity |
| 重复外部副作用 | 0 |
| 事件重放 | 状态一致 |

浏览器检查覆盖 1600×1000 桌面和 760×1000 窄屏；窄屏 `scrollWidth = clientWidth = 760`，控制台错误 0、警告 0。截图、SQLite 事件库和结构化回执位于 `artifacts/goal/m25-s1-live-lookdev/`。
