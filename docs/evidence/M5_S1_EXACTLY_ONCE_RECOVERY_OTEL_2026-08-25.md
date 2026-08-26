# M5-S1：Exactly-once 恢复与 OpenTelemetry 证据

## 结论

冻结故障矩阵共 6 个案例，6/6 通过，重复副作用 0。真实主运行新增第 16 个 append-only 事件 `recovery_scorecard_recorded`，没有新增人工批准或待决状态。

这轮没有调用真实 provider、没有重新生图、没有修改 Unreal，也没有发布到项目之外。候选采用、修订和最终本地发布仍由 Codex 编排器自主负责。

## 冻结矩阵

| 案例 | 恢复结果 | provider 副作用 | 终态事件 | 重复 |
| --- | --- | ---: | ---: | ---: |
| `before_reservation` | 成功恢复 | 1 | 1 | 0 |
| `after_reservation` | 成功恢复 | 1 | 1 | 0 |
| `after_submit` | 复用 provider request，成功恢复 | 1 | 1 | 0 |
| `completion_unknown` | 安全保持未知，禁止重提 | 1 | 0 | 0 |
| `after_artifact_persistence_before_event_commit` | 重新校验制品并提交唯一终态 | 1 | 1 | 0 |
| `adoption_revision_replay` | 事件重放不追加副作用 | 1 | 1 | 0 |

采用事件保持 1 次；局部修订的两个事件共享同一个原始生成制品哈希，因此外部生图副作用为 1 次。第一次硬边合成失败和第二次本地羽化纠正都被保留，但没有再次调用生图。

## 可观测性边界

- 使用官方 `opentelemetry-sdk`，输出 W3C 兼容 32 位 trace ID、16 位 span ID 与 `traceparent`。
- `invoke_agent`、预留、查询、提交、恢复确认和制品校验 span 通过 run ID、execution ID、event sequence、capability ID 与结果关联。
- idempotency key 和 provider request ID 仅记录 SHA-256。
- exporter 采用显式字段白名单，不记录 prompt、图像字节、凭据、授权头或隐藏推理。
- 重启会产生新的 trace，但通过稳定的 run/execution 身份与事件序列关联；本切片没有宣称跨进程 parent span 连续性。

## 可检查制品

- `artifacts/goal/m5-s1-recovery/recovery-scorecard.json`
- `artifacts/goal/m5-s1-recovery/traces/after_submit.json`
- `artifacts/goal/m5-s1-recovery/cases/*/agent-events.sqlite3`
- `artifacts/goal/m5-s1-recovery/recovery-panel-wide.png`
- `artifacts/goal/m5-s1-recovery/recovery-panel-narrow.png`

Scorecard SHA-256：`384e7c536f795900d62328bbf607fd5e8a51767a6e3cda349e03f3dacfcb1dc4`。

## 限制

- 故障来自确定性的本地夹具，不代表真实网络故障分布。
- 延迟是本机重启与协调耗时，不是 provider 网络延迟。
- completion-unknown 没有 provider 证据时故意不成为成功终态。
- 治理内存、完整 Harness 冻结评测、Unreal 回写和 C2PA 交付仍待后续切片证明。

## 验收

- Python 全量：92 passed。
- quick 门禁：98 passed（包含脚本级状态审计）。
- 前端生产构建：1,804 modules transformed。
- 目标审计：revision 27，下一切片 `M5-S2`，通过。
- Playwright：1440×1000 与 390×844 均无横向溢出、无破图、控制台 0 错误；恢复面板宽/窄截图已持久化。
- 本切片涉及的 Python 文件通过 Ruff；仓库全局 Ruff 仍有 4 个既存格式项，不影响 quick 门禁，未借本切片改动无关文件。
