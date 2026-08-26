# M5-S3 冻结 Agent Harness 与作品集记分卡

## 结论

版本化冻结套件在真实主运行上通过 20/20 个命名案例，覆盖上下文、能力边界、模型路由、策略门禁、故障恢复与记忆治理。记分卡以内容哈希写入第 24 个 append-only 事件，重放不会重新计时或制造第二次副作用。

## 可核验指标

| 指标 | 结果 | 分母与边界 |
| --- | ---: | --- |
| Harness 任务通过率 | 20/20 | 冻结套件全部命名案例 |
| 上下文案例召回 | 3/3 | 深埋硬约束、陈旧观察排除、无关记忆排除 |
| 路由与策略准确 | 5/5 | 能力不可用、隐私/成本上限、误打断、审批指纹、硬门禁优先级 |
| 误打断 | 0/1 | 本地安全路由案例 |
| 重复副作用 | 0/5 | 已有恢复套件的副作用案例 |
| 外部夹具成本 | $0/20 | 本轮不调用 provider |

延迟仅是本机冻结夹具的执行时间，不代表生产 provider 延迟；20/20 也不代表开放域生图质量。恢复与记忆结果引用已有记分卡哈希，不复制或改写来源结论。

## 证据

- `artifacts/goal/m5-s3-harness/harness-scorecard.json`
- `artifacts/goal/m5-s3-harness/harness-panel-wide.png`
- `artifacts/goal/m5-s3-harness/harness-panel-narrow.png`
- `src/artflow_agent/harness_eval.py`
- `src/artflow_agent/harness_contracts.py`
- `tests/test_harness_eval.py`

真实运行事件状态：sequence 24，Harness 记分卡哈希 `c5cf993177b19f27c32a1e3a965ff64eb624b19d02ccac4fc04ea837445bdf8b`，无待处理决策。
