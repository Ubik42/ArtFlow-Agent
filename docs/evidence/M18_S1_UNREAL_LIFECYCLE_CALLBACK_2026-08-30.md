# M18-S1：Unreal 原生场景变体生命周期回传

## 结论

ArtFlow Scene Bridge 已能把候选评价、采用、发布和审阅结果直接回传到当前 Scene Session。四次回传均由独立 Unreal Engine 5.8.1 命令行编辑器进程完成，最终事件流严格保持：创建运行、挂接场景、启动 Session、评价、采用、发布、审阅，共 7 条事件。

回调只提交转换名称、当前 Session 哈希、注册制品哈希和动作身份。制品路径与具体结构由 Agent 在项目内解析；调用方路径字段、未知内容身份、乱序转换和复用动作身份篡改内容均会被拒绝。

## 实现边界

- Unreal Bridge 通过仅监听 localhost 的固定接口回传，不开放任意 URL、脚本或事件结构。
- 服务端从 M12–M16 已冻结制品建立内容身份索引，索引不是第二套生命周期状态库。
- 所有合法回调仍写入原有 `AgentEventStore`，并由同一 Reducer 生成 `AgentRunProjection`。
- 相同动作重放保持幂等；即使后续事件已经存在，Unreal 也按时间线中目标事件进行确认，而不是错误依赖最后一条事件。
- M16 固定迁移接口只保留为兼容性夹具，不再是正常宿主路径。

## 实机证据

| 项目 | 结果 |
| --- | --- |
| Unreal 版本 | 5.8.1 |
| 独立宿主回调 | 4 / 4 |
| 生命周期事件 | 4 条，总事件 7 条 |
| 事件顺序 | evaluation → adoption → publication → review |
| 调用方路径字段 | 0 |
| Unreal 插件编译 | `ArtFlowBridgeHostEditor Win64 Development` 成功 |

机器可读汇总位于 `artifacts/goal/m18-s1-unreal-callback/verification.json`，四份 Unreal 宿主回执位于同目录 `host-receipts/`，服务端最终投影位于 `live-projection.json`。

## 高价值验证

聚焦验证覆盖了合法四阶段、乱序、未知身份、额外路径字段、非本机请求、相同动作重放和相同动作篡改身份；未扩大到浏览器矩阵、全事件覆盖率或重复视觉验收。
