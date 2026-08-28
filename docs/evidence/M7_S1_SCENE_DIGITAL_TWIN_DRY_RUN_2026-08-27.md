# M7-S1 证据：Scene Digital Twin 与灯光/PCG 零写入计划

日期：2026-08-27

宿主：Unreal Engine 5.8.1 / ArtFlowBridgeHost

插件：ArtFlow Scene Bridge 1.1.0

## 结论

M7-S1 已完成。真实 UE 5.8 关卡能够在同一个原子 Scene Package 中导出四个 Render Pass、三维
Scene Digital Twin、受限灯光/PCG SceneChangePlan 和 dry-run receipt。独立验证器确认计划绑定到
同一份三维事实，目标是 `ArtFlow_KeyLight` 和真实 `UPCGComponent`，且 dry-run 前后源 `.umap`
SHA-256 完全一致。

这不是三维执行完成声明。M7-S1 只证明“看得见、计划得出、不会误写”；暂存关卡的实际灯光/PCG
执行、同机位回渲和清理属于 M7-S2。

## 真实宿主结果

| 项目 | 结果 |
| --- | --- |
| 独立 UnrealEditor PID | `48740` |
| 启动前已有 UnrealEditor | 0 |
| 退出后残留 UnrealEditor | 0 |
| 运行结果 | success |
| Scene Package | `artflow-ue-367938ea4fff2d57cb2176a7a45bbad1` |
| Archive SHA-256 | `e9de9b1b2789c76d0e51467c330a88d081f98f6ed75b46e37cb939ebfd053050` |
| Actor / Light / PCG | 21 / 2 / 1 |
| 计划操作 | `set_lighting_rig`、`apply_pcg_layout` |
| 暂存策略 | `candidate_level`（fixture 非 World Partition） |
| committed mutations | 0 |
| 源 map 运行前 SHA-256 | `620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a` |
| 源 map 运行后 SHA-256 | `620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a` |

宿主从 `2026-08-28T02:38:55.612Z` 启动，`02:39:12.036Z` 写出成功结果，并在
`02:39:14.497Z` 关闭日志。测试使用隐藏的独立 GUI 进程，未附着或关闭用户会话。

## 合同与失败边界

- Scene Digital Twin 拒绝重复 Actor ID/GUID、反向 bounds、缺失指纹、重复材质槽/PCG ID，以及
  `protected=true` 且 `editable=true`；
- SceneChangePlan 使用判别联合，只接受 `set_lighting_rig` 和 `apply_pcg_layout`；
- 计划拒绝未知操作、额外脚本字段、自依赖、未知依赖和依赖环；
- 每个操作都绑定 source fingerprint、write scope、idempotency key、预算、验证器和 cleanup；
- 独立验证器重新计算 ZIP、Twin、Plan、源 map 哈希，并核对灯光/PCG 目标和保护对象不变量。

## 可检查证据

- `artifacts/goal/m7-s1-scene-dry-run/scene-package.zip`
- `artifacts/goal/m7-s1-scene-dry-run/verification.json`
- `artifacts/goal/m7-s1-scene-dry-run/host-lifecycle.json`
- `contracts/scene-digital-twin.v1.schema.json`
- `contracts/scene-change-plan.v1.schema.json`
- `contracts/scene-dry-run-receipt.v1.schema.json`
- `scripts/verify_scene_dry_run.py`
- `tests/test_scene_delta_contracts.py`
