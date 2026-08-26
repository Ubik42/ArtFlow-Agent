# ArtFlow Agent 作品集案例

## 一句话

ArtFlow 把 Unreal 场景事实和美术意图编译成有界生成任务，能够从失败中恢复、拒绝漂亮但生产不可用的结果，并把证据选中的资产带着可验证来源回流 Unreal。

## 问题与判断

ComfyUI 和图像模型擅长生成，但真实美术生产还要求：相机不能漂、保护区域不能改、节点和模型必须在当前机器可用、昂贵调用不能因重试重复、生成器不能给自己打分、最终结果要能解释为什么被采用。把这些责任都塞进 prompt，只会得到一个看起来像 Agent 的聊天壳。

ArtFlow 把模型决策与确定性控制层分开。模型只看受控 Context 和闭合 tool schema；自研 Harness 拥有状态、策略、工具权限、幂等、验证、恢复、记忆和证据。

```text
Human Art Direction + Unreal Scene Facts
                    │
            Context Assembler
                    │
       Planner / Capability Router
                    │
     deterministic policy + identity
           ┌────────┴────────┐
      Local ComfyUI      Codex GPT Image 2
           └────────┬────────┘
        Constraint Judge + Visual Critic
                    │
        evidence-backed Codex adoption
                    │
        mask-bounded correction + verifier
                    │
        typed Unreal return + provenance
```

这是一个 durable coordinator 加有界角色，不是开放式多 Agent 聊天室。Provider Executor 不能参与评价或采用；Visual Critic 不能覆盖确定性失败；Codex Orchestrator 不能删除 dissent。

## 黄金路径

1. UE 5.8 Bridge 从 `ArtFlowDemo` 捕获 beauty、depth、world normal 和 object ID，记录相机、保护/编辑对象与逐文件 SHA-256。
2. Context Assembler 保留硬约束与状态栏，只注入最近观察和同项目精确命中的生产记忆。
3. Router 根据真实 RTX 4080 / ComfyUI 节点模型清单、隐私等级和成本上限选择可执行能力。
4. 本地 ComfyUI 与 Codex 内置 GPT Image 2 在同一 Scene Package 与美术意图下各生成一个候选。
5. Deterministic Tribunal 检查尺寸、构图、相机和保护域；独立多模态 Critic 判断视觉方向并保留分歧。
6. 一个更吸引人的负对照因相机和结构越界被硬拒绝，无法参加排序。
7. Codex 编排器按已持久化证据采用合格候选，随后只在右侧球体蒙版内执行一次有界修订。
8. Pixel guard 证明蒙版外 1,530,358 个像素变化为 0，修订通过。
9. typed return tool 把资产写入 `/Game/ArtFlow/Returns`，在 `/Game/ArtFlowDemo` 创建来源绑定 Actor，UE 内容验证和可见截图通过。
10. 独立验证器检查 9/9 来源文件绑定，最终本地发布包再次验证全部收录文件和核心身份。

## 最重要的失败路径

恢复矩阵在五个副作用边界以及采用/修订重放上注入崩溃：reservation 前后、submit 后、completion unknown、文件已落盘但事件未提交。Agent 通过 idempotency key、reserve/submit/reconcile、不可变 receipt 和 reducer 重放完成 6/6 恢复，五个有外部副作用的案例均未重复执行。

这比“捕获异常再 retry”更重要：timeout 只表示结果未知，不能证明 provider 没有接收请求。

## 可量化证据

| 结论 | 数据集与分母 | 结果 |
| --- | --- | ---: |
| 冻结 Harness | 20 个命名 context/capability/routing/policy/recovery/memory 案例 | 20/20 |
| Context 召回 | 深埋约束、陈旧观察排除、无关记忆排除 | 3/3 |
| 路由与策略 | 能力、隐私、成本、指纹、硬门禁案例 | 5/5 |
| Recovery | 六个冻结故障场景 | 6/6 |
| 重复副作用 | 五个包含 provider/adoption/revision 副作用的恢复场景 | 0/5 |
| Memory governance | 来源、版本、冲突、scope、检索案例 | 6/6 |
| 局部修订越界 | 蒙版外 1,530,358 像素 | 0 个变化 |
| 来源文件绑定 | 当前项目本地来源链 | 9/9 |
| Harness 外部成本 | 20 个本地冻结夹具案例 | $0 |

这些数字不代表开放域生图质量或生产 provider 延迟。视觉采用是一个真实项目样例，不被包装成统计意义上的 human adoption rate。

## 工程取舍

- 不暴露任意 ComfyUI 图：牺牲一点自由度，换取节点/模型兼容、参数审核和可重放。
- 不用框架替代状态机：PydanticAI 只做 typed model boundary；SQLite reducer 与策略保持项目可解释性。
- 精确检索先于向量库：当前生产记忆只有明确 subject key；没有测得召回问题前不引入 embeddings。
- 独立评价先于自评：provider receipt 与 Tribunal 分离，避免生产者同时当裁判。
- 自动采用而非反复确认：项目内采用与发布由编排器依据证据负责；只有越出项目边界的公共或不可逆操作才打断用户。
- 诚实的 C2PA 边界：当前只做 C2PA 2.4 vocabulary-compatible unsigned sidecar。哈希链可验，但没有签名证书。

## 五分钟讲解节奏

1. 看真实 Scene Package 与对象区域，不从聊天框开始。
2. 展示双 Provider 同源约束、路由选择与 receipt。
3. 展示负对照：Visual Critic 喜欢，但 deterministic gate 拒绝。
4. 展示自主采用和 before/after，强调蒙版外 0 像素。
5. 展示 recovery 6/6、memory 6/6、Harness 20/20，说明它们是命名 fixture。
6. 最后落到 UE 回流和 9/9 来源链，主动指出 unsigned C2PA 限制。

操作顺序见 [DEMO_GUIDE.md](DEMO_GUIDE.md)，原始证据见 [`docs/evidence/`](evidence/)。
