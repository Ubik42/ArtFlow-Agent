# M9-S1：材质、PCG、灯光与资产复用的统一 Scene Delta dry-run

本切片把前三条已经分别验证过的 UE 能力路线收敛为同一个 `scene-delta-plan/2`，没有创建第二套
Agent 状态机。计划中的每项操作都带领域、依赖、源指纹、写入范围、幂等键、预算、技术验证器、
不确定性、最小变更等级、能力偏好和补偿策略；模型不能夹带 Python、Blueprint、Shell 或任意图。

## 冻结的废墟祭坛计划

```text
第一准备波（最多 3 路并行）
  asset-reuse      → 项目自有 SM_ArtFlowRock
  lighting-patch   → 5.5 / 4200K
  material-bind    → M8 已验证的玄武岩 Material Instance

第二准备波
  pcg-layout       → 依赖 asset-reuse + material-bind

唯一 UE 写入通道（严格串行）
  asset-reuse → lighting-patch → material-bind → pcg-layout
```

图生 3D capability 被刻意标记为 unavailable；Router 没有中止或要求人工授权，而是按最小变更策略
自动选择 `asset.catalog.reuse.v1`。PCG 仍只能使用固定
`/Game/ArtFlow/PCG/PCG_ArtFlowScatter` 与受审 graph hash，参数仅为密度、资产集合和确定性 seed。

## 失败域纠正边界

dry-run 为四个领域分别生成 reopen 集：材质失败只重新打开 `material-bind`，灯光失败只打开
`lighting-patch`，PCG 或资产目录同理。依赖下游会暂停应用，但不会重新调用已成功的 Provider；这为
M9-S2/S3 的真实纠正与恢复提供了稳定身份。

## 负对照与证据

独立验证 6/6 通过并在任何宿主写入之前失败关闭：

1. 任意代码字段；
2. 保护对象成为写入目标；
3. DAG 依赖环；
4. Actor 预算超限；
5. 源对象指纹陈旧；
6. PCG graph hash 未被 capability attestation 覆盖。

冻结计划 SHA-256 为 `bfbc36e2c2c4eee433885f1e8ebdd6b1e0bc1a1d9698cde276eebbbb31343df3`，
dry-run receipt SHA-256 为 `3fb05bf22c293fb4244406ef97955b8222d3fea32018873a94b15288f70dd2c0`，
提交 mutation 数为 0。机器证据位于 `artifacts/goal/m9-s1-multi-domain-dry-run/`，可重放输入位于
`examples/m9-*.json`。

该结果证明联合计划、能力降级、并行准备/串行写入和失败域身份，不声称已执行最终多域 UE 变更。
M9-S2 将把同一合同绑定到真实 Scene Digital Twin，应用到候选关卡并增加验证机位回渲。
