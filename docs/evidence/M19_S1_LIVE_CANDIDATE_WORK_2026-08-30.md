# M19-S1：当前 Scene Session 的 Unreal 候选工作项

## 结论

ArtFlow 已把实时 Scene Session 的 Candidate Plan 转换为可由 Unreal 原子领取的注册工作项。产品入口位于 Unreal 编辑器 Tools 菜单“执行当前 ArtFlow 候选”；领取后使用既有受限 PCG 与灯光执行器，在请求派生的隔离关卡完成生成、宿主复检和结果回传。

本次实测先由 UE 5.8.1 重新导出当前 `/Game/ArtFlowDemo`，建立全新的 Run 与 Scene Session，再从该 Session 编译工作项。整个过程不读取 M12 历史 Scene Package。独立 UE 进程生成 12 个 PCG 实例，源关卡哈希保持不变，最终投影包含 8 条事件。

## 状态与边界

```text
Scene Session
  → queued
  → claimed（单一 Unreal 写入者）
  → executing
  → reconciling
  → succeeded / failed
```

- 工作定义同时绑定 Run、Session、Stage Request、Candidate Plan 与内容哈希。
- 第二个 Worker 不能抢占已领取工作项。
- Unreal 只有在服务端确认 `executing` 后才进入候选写入。
- 候选生成后先进入 `reconciling`，核对宿主回执哈希后才进入 `succeeded`。
- 前置身份或指纹过期会回传 `failed`；源关卡不会被候选写入覆盖。
- 调用方不能提交主机路径、脚本、任意 Plan 或自定义工作流。

## 实机结果

| 项目 | 结果 |
| --- | --- |
| Unreal Engine | 5.8.1 |
| 当前运行 | `unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e` |
| 当前工作项 | `scene-work-807e766c4393` |
| 持久事件 | 8 |
| PCG 实例 | 12 |
| 源关卡变化 | 0 |
| 最终状态 | `succeeded` |

机器可读验证位于 `artifacts/goal/m19-s1-candidate-work/verification.json`；最终投影、Unreal 宿主回执和桌面/窄屏中文截图位于同一目录。

## 验证范围

自动验证集中覆盖工作定义身份、原子领取、合法状态迁移、重放恢复、第二写入者、路径字段和非本机调用。UE 实机验证使用一个独立短生命周期进程；启动前不存在 UE 5.8 进程，完成后该进程退出。验证期间出现的 UE 5.7 Lyra 进程属于其他任务，未附着或关闭。
