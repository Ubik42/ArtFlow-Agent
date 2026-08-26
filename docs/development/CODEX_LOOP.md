# Codex /goal 持续开发循环

## 单一事实来源

恢复顺序固定为：

1. `config/goal-state.json`：机器状态、依赖图、唯一下一切片、风险和停止条件；
2. `lastCheckpoint` 指向的 checkpoint：上一已验收切片的事实；
3. 当前代码、测试、Git 状态和内容寻址 artifact：发现状态漂移时拥有更高事实权重；
4. `docs/AGENT_ENGINEERING_BLUEPRINT.md`：Agent 架构、作品集证据和反偏移规则；
5. `docs/development/CODEX_GOAL.md`：不会随实现细节改变的产品完成定义。

聊天记录、TODO 列表和模型记忆都不是进度数据库。

## 开始一轮

```powershell
.\scripts\goal.ps1 -Action Resume
.\scripts\goal.ps1 -Action Doctor
```

`Resume` 只读取和解释状态；`Doctor` 校验状态语义并检查当前切片声明的环境要求。任何目标文件中的 `validationCommands` 都只是审阅清单，脚本永远不把它们作为字符串动态执行。

恢复时必须：

- 读取仓库 `AGENTS.md`；
- 读取 goal、完成定义、循环和 checkpoint；
- 保存用户已有工作，不能通过 reset/checkout 清理脏树；
- 对比状态声明与可观测代码；冲突时先修状态，不带着假前提开发；
- 用户的新指令可以替换下一切片，但要把方向变化落回状态与 checkpoint。

## 选择切片

任一时刻只能有一个 `in_progress` milestone 和一个 `nextSlice`。切片必须声明：

- 可观察 outcome；
- 风险等级 R0–R4；
- 本轮最多能达到的证据等级 A1–A5；
- 是否需要真实 DCC；
- 允许修改路径；
- 明确 non-goals；
- 可执行 acceptance；
- stop conditions；
- 当前环境要求；
- 明确列出的验证入口。

优先级为：真实用户价值 → 可靠性和可验证性 → 扩展性 → 性能体验。展示材料不能成为默认主线阻塞项。

## 实现规则

1. 先建立严格合同与失败案例，再接模型或 UI；
2. 路由先收敛候选能力，再向模型暴露闭合 tool schema；
3. 项目内读写、本地算力、候选采用、局部修订、UE 回写验证与本地发布默认自主执行并记录差异；只有越出项目边界的不可恢复或公共副作用才请求人工确认；
   新视觉生成只走 Codex 内置 GPT Image；采用与最终本地发布由编排器依据持久评价自主完成；
4. 读检查器可以有限并行，共用资源写入必须按 scope 串行；
5. 每个节点拥有输入/输出哈希、幂等身份、timeout、retry 和 terminal semantics；
6. 大型工具输出进入 artifact，Context 只接收受控摘要和 citation；
7. 不在当前切片顺手加入框架、页面或宿主支持。

## 验证与证据

```powershell
.\scripts\goal.ps1 -Action Audit
.\scripts\validate.ps1 -Tier quick
```

验证必须包括当前切片的故障路径。命令退出 0 只证明测试进程通过；业务结论仍需由合同、当前 artifact 和独立 verifier 支撑。

真实宿主规则：

- `requiresRealHosts=false` 的切片不得为了“顺便验证”启动 DCC；
- 后台 disposable 运行不能证明可见宿主；
- Computer Use 只用于选定窗口的可见交互，使用当前返回的窗口句柄，每步重新观察；
- 不自动抢占用户桌面，不操作 ChatGPT/Codex UI，不通过 UI 打开终端；
- 用户明确置于本项目范围内的 UE 工程、测试资产和本地制品由 Codex 自主操作；共享安装、无关用户数据、公共上传及越出项目边界的不可逆动作才需要另行确认。

## Checkpoint 与推进

只有 acceptance 和规定门禁通过后，才允许：

1. 写入下一个顺序 checkpoint；
2. 更新 `lastCheckpoint` 和 `stateRevision`；
3. 完成当前 milestone 或选择它的下一切片；
4. 保留真实 evidence ceiling 和 unresolved risks。

Checkpoint 记录 changed areas、验证数量、当前证据、风险和唯一下一切片；不保存思维链、prompt、密钥、绝对路径和冗长日志。

## 阻塞语义

- `status=active` 时 `currentBlocker` 必须为空；
- 一次失败不是 blocker：先尝试只读诊断、替代验证和安全降级；
- 同一不可绕过条件连续出现，且无法推进当前 slice，才记录 blocker 和恢复条件；
- 人工轨道默认不阻塞主线，除非它被显式提升为当前切片；
- blocked 状态不能靠改字段解除，必须重新检查恢复条件并记录新 checkpoint。

## 状态审计防线

`scripts/validate_goal_state.py` 负责检查：

- milestone 唯一性、依赖存在性与无环性；
- 完成状态不能依赖未完成阶段；
- active 状态恰好一个 in-progress milestone；
- next slice 与 current milestone 一致；
- allowed path 不能是绝对路径或目录穿越；
- 验证命令只能来自固定安全前缀，且不会被动态执行；
- blocker、人工轨道和 checkpoint identity 一致。

JSON Schema 保留为线协议文档；跨 PowerShell 5/7 的实际门禁统一由 Python 校验器执行，不依赖仅部分 PowerShell 版本提供的 `Test-Json`。

这套审计保护持续开发状态本身，不能替代产品测试。
