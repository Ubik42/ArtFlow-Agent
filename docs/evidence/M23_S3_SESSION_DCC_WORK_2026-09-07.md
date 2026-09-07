# M23-S3 · Scene Session 持久 DCC 工作项

已验证的 Blender 建模、ComfyUI PBR 装配与 Unreal 候选回流不再是孤立脚本。ArtFlow 将两个固定能力版本、建模请求、PBR 请求、Unreal 回执和候选关卡身份编译为 `artflow-scene-dcc-work/1`，并写入当前 Scene Session 使用的同一 append-only SQLite 事件账本。

| 项目 | 实测结果 |
| --- | --- |
| DCC 工作身份 | `dcc-work-47533c33f0a3` |
| Scene Session | `scene-session-dc31f6ed0f4e` |
| 生命周期 | queued → claimed → executing → reconciling → succeeded |
| 最终结果身份 | Unreal return receipt `6213c1e153c3…` |
| 事件重放 | 42 个事件重建为相同 succeeded 状态 |
| 外部生成重复 | 0 |

场景变更谱已加入“派发 Blender DCC”产品入口，并在当前版本轨道中显示“ComfyUI PBR → Blender → Unreal”与内容身份。桌面浏览器实测可见“Blender DCC · 已回流”，中文文案、状态和候选谱系同时成立。

这一工作项复用 `AgentEventStore`、现有 reducer、SSE 投影和单一工作者迁移规则，没有新增数据库、调度框架或审批流程。固定编译器只读取项目注册制品，不接受调用者提供 Python、路径、命令或 ComfyUI graph。
