# M5-S2：证据治理的生产记忆

## 结论

ArtFlow 现在拥有小型、手写、事件溯源的生产记忆层，而不是泛化聊天记忆或 RAG 包装：

- episodic：冻结恢复矩阵的真实运行经验；
- semantic：当前 Unreal 场景的机位与构图约束；
- procedural：局部修订接缝出现时复用原始生成制品、仅在遮罩内纠正的方法。

三条真实记录均由 Codex 编排器在项目作用域内自主激活，分别引用真实事件哈希。主运行从 16 增长到 23 个 append-only 事件，没有人工批准或 pending decision。

## 治理机制

模型或编排层只能提交 `MemoryProposal`；权威状态机负责：

1. 验证 project ID、source run 和全部 source event hash；
2. 校验内容哈希、版本、作用域和 supersession lineage；
3. 使用 `project-memory-policy/1` 确定性激活或拒绝；
4. 只检索 active、同项目、精确 kind/subject/tag 匹配的记录；
5. 返回原始事件哈希 citation，不把索引当作事实源。

项目私有来源请求提升到 `shared` scope 时必定以 `shared_scope_authority_missing` 拒绝。当前没有向量库、embedding 服务、跨项目共享或个人聊天记忆。

## 冻结评测

`m5-s2-memory-suite/1` 共 6 个案例，6/6 通过：

- 激活、重启和幂等重放；
- 未声明 supersession 的冲突拒绝；
- stale version 拒绝；
- 项目私有证据提升 shared scope 拒绝；
- forged source event hash 拒绝；
- 精确相关检索与无关记录过滤。

冻结案例中的检索 precision 为 1.0，冲突类拒绝率为 1.0。该数字只适用于明确列出的 6 个本地确定性案例，不代表开放域语义召回。

## 可检查证据

- `src/artflow_agent/production_memory.py`
- `src/artflow_agent/memory_eval.py`
- `scripts/run_memory_suite.py`
- `artifacts/goal/m5-s2-memory/memory-scorecard.json`
- `artifacts/goal/m5-s2-memory/memory-eval-events.sqlite3`
- `artifacts/goal/m5-s2-memory/memory-panel-wide.png`
- `artifacts/goal/m5-s2-memory/memory-panel-narrow.png`

Scorecard SHA-256：`356506f64eecca2aa6b401870c2552a309d5807b7eb739f2712d32cd4b6097dc`。

## 限制

- 当前检索是精确元数据查询，不声称语义召回能力。
- shared scope 尚无独立 authority contract，因此只会拒绝，不会暂停等待人工批准。
- 评测在真实事件数据库的本地备份上运行，没有调用 provider、生图或修改 Unreal。
- 完整 Harness 汇总评测、Unreal 回写与 C2PA 交付仍待后续切片证明。

## 验收

- Python 全量：96 passed。
- quick 门禁：102 passed（包含 Goal 与脚本级审计）。
- 前端生产构建：1,804 modules transformed。
- 目标审计：revision 28，下一切片 `M5-S3`，通过。
- Playwright：1440×1000 与 390×844 无横向溢出、无破图、控制台 0 错误。
- 本切片相关 Python 文件通过 Ruff，`git diff --check` 无 whitespace error。
