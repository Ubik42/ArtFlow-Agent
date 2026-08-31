# M15-S1 · 候选采用与版本化 Unreal 发布

## 结果

晴光庭院的修正候选已经由 Codex 编排器根据持久评价证据正式采用，并发布为唯一的内容寻址
Unreal 场景变体：

`/Game/ArtFlow/Published/AF_784907467248/V_baeeeb76ada9`

采用决定同时绑定领域评价、Candidate Plan、UE 执行回执、源关卡与候选关卡哈希。发布工具只接受
已注册策略和项目自有 Session 目录，不能由模型指定任意目标路径。

## 实机验证

| 项目 | 结果 |
| --- | --- |
| 首次 UE 5.8 宿主运行 | `published` |
| 新 UE 5.8 进程重放 | `reconciled` |
| Published 场景包 | 1 |
| 重复场景包或外部副作用 | 0 |
| PCG 实例 | 12 |
| 保护对象状态 | 与采用决定一致 |
| 材质绑定 | 与采用决定一致 |
| 源 `ArtFlowDemo.umap` | 发布前后 SHA-256 完全一致 |

源关卡 SHA-256 为
`620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a`；发布场景包 SHA-256 为
`88177f197a9b727525dabf2c9132f2b9e7aa7af3ad89ffc674ab1e8bf03e1cf2`。新进程通过发布元数据与
内容身份对账，没有再次复制关卡。

## 失败关闭

6 个聚焦合同测试覆盖正常采用以及 5 个负对照。以下输入不能形成有效发布：

- 仍需纠正的领域评价；
- 评价后被改动的候选关卡；
- 候选执行后被改动的源关卡；
- 手工指定的 Published 目标；
- 未注册的采用策略版本。

## 冻结证据

- `artifacts/goal/m15-s1-session-publish/adoption-decision.json`
- `artifacts/goal/m15-s1-session-publish/publish-request.json`
- `artifacts/goal/m15-s1-session-publish/publish-receipt.json`
- `artifacts/goal/m15-s1-session-publish/publish-reconcile-receipt.json`
- `artifacts/goal/m15-s1-session-publish/verification.json`

本切片没有重新调用 GPT Image、ComfyUI、资产导入或 PCG；它只采用已经通过评价的精确候选，
并把“候选已通过”推进为可对账的 Unreal 发布事实。
