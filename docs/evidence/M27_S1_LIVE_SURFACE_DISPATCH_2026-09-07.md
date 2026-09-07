# M27-S1 · Live Surface Bake dispatch

M26 实测的 UV 与材质 Bake 已成为当前 Scene Session 的第六项 DCC 能力。

![场景变更谱中的 Surface Bake 路线](../../artifacts/goal/m27-s1-live-surface/live-surface-route.png)

## 产品路径

1. `scene-dcc-work/queue` 从当前 Session 和冻结制品编译唯一工作身份，依次绑定建模、PBR、Geometry Nodes、镜头灯光、Lookdev 与 Surface Bake。
2. 原有本地 Worker 领取工作项，重新验证 M26 请求、Blender 五项制品、Unreal 回执和截图的内容身份。
3. `queued / claimed / executing / reconciling / succeeded` 五个事件写入原有 append-only 账本；重复派发保持同一个 Work。
4. 场景变更谱展示 Lookdev 输入、`ArtFlow_BakedUV` 图集、Blender 可编辑结果和 Unreal 隔离候选。

## 固定结果

| 项目 | 结果 |
| --- | --- |
| Work | `dcc-work-5160e7d8d699` |
| 登记能力 | 6 / 6 |
| DCC 生命周期事件 | 5 个 |
| Surface Request | `9cbf7f1f…7bf55` |
| 最终候选 | `/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Surface_B_9cbf7f1f20ab` |
| 重复派发 | 相同 Work identity |
| 重复外部副作用 | 0 |
| 事件重放 | 状态一致 |

浏览器检查覆盖 1600×1000 与 760×1000，页面横向溢出为 0；四张产品媒体均成功加载，控制台错误与警告为 0。截图、SQLite 事件库和结构化回执位于 `artifacts/goal/m27-s1-live-surface/`。
