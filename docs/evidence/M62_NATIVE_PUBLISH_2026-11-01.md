# 当前发布动作自动采集原生候选事实

发布按钮原本直接领取 publish-request，该请求依赖已经存在的候选快照。新候选需要手工运行检查脚本，才能进入发布。本次把检查串入同一个登记的 publish_session_candidate.py：

1. 从当前运行账本领取 inspection-request，验证采用身份、评价引用和源/候选文件摘要。
2. 在现有 UE 宿主内调用固定只读检查，加载确切候选，记录保护对象、材质与实例数。
3. 领取既有 publish-request；若采用身份在两次请求间变化，立即停止。
4. 复用现有发布、对账和回执路径，保留同一个事件账本。

## 实际验证

将原候选事实文件移到本工程 artifacts 保留，确认发布前没有事实文件。单次产品脚本调用自动重新采集 18 个实例，返回 reconciled 并复用既有 Published 版本。第二个独立 UE 进程重复调用，仍返回同一版本。

- 源关卡和采用候选的文件 SHA-256 均未变化。
- 发布文件摘要为 a48e511e284a4d50c019046ce6ec5db0080711f70cc11230d24b28de599c43ea，与既有版本一致。
- duplicate_side_effect_count=0，source_save_count=0。
- 206 项 quick 检查通过；合同 schema 导出完成。新增检查覆盖不依赖旧事实的身份领取、场景字节变化拒绝与本机访问范围。
- 首次环境启动缺少 Python 模块，随后使用工程 .venv 启动 API；失败日志保留。实际引擎调用使用 UE 5.8.1 Commandlet，此批不新增画面质量结论。

入口：启动工程 API 后运行 `scripts/run_current_publish.ps1 -RunId <当前运行ID>`。UE 插件现有发布按钮调用同一 Python 入口，检查逻辑无需新增按钮或审批。

公开摘要与事实在 `docs/evidence/m62`；完整日志和原事实备份在 `artifacts/goal/m62-s1-native-publish`。本次继续已有 M61 的 Agent 账本与已采用候选，未重新生成 ComfyUI 或 Blender 资产。
