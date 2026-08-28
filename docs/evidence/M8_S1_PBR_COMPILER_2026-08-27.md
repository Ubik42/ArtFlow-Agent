# M8-S1：能力门禁式 ComfyUI PBR 图编译器

本切片把 ComfyUI 从“Agent 可以自由拼画布”的风险面，收敛为“Agent 只能给受审模板填有限参数”的
生产能力。它验证了真实宿主、真实自定义节点和真实 API 图，但没有提交 GPU 生成任务，也不声称已经
得到五张贴图或完成 Unreal 材质回贴。

## 实机能力证据

- ComfyUI：`0.28.0`；Python：`3.12.13`；PyTorch：`2.13.0+cu130`。
- `ComfyUI-Production-Nodes`：commit `d102528b8f2418b98551eeb9aa3841116206a61c`，MIT。
- 隔离探测宿主：`127.0.0.1:8190`，项目自有 base/user/database，CPU 能力探测模式。
- 节点总数：826；模板所需节点：19/19；Production Nodes：8/8 可见。
- 共享 `127.0.0.1:8188` 保持原进程和 1301 节点，未安装 sibling 自定义节点。
- 探测结束后 8190 端口为空，两个隔离进程均已结束；共享父/监听 PID 仍为 39904/49656。

隔离宿主只通过 allowlist 加载 `ComfyUI-Production-Nodes` 的项目运行副本。最终复测使用项目内独立
SQLite URL，未再争用共享数据库。生命周期事实见
`artifacts/goal/m8-s1-pbr-compiler/host-lifecycle.json`。

## 受审图与编译边界

项目冻结 `pbr-material-v1.workflow.json`，包含 49 个节点与五条生成分支：Base Color、DirectX
Normal、Roughness、Metallic、Ambient Occlusion。模板 manifest 同时绑定：

1. 规范化 workflow SHA-256；
2. 19 个允许出现的 `class_type`；
3. 每个节点来自真实 `/object_info` 的接口 schema SHA-256；
4. 三个模型文件身份；
5. 仅 19 类有限插槽目标，包括输入图片、提示词、种子、尺寸、denoise、合同和输出前缀。

模型不能提交节点、连线、Python、Shell 或任意路径。编译请求只接受项目输入命名空间
`ArtFlow/...`，Pydantic 的 `extra=forbid` 会拒绝夹带字段；模板字节对应的规范化图、节点集合或接口
指纹任一漂移，都会在 `/prompt` 提交前失败。

Production Nodes 中的 Constraint/Contract/Receipt 节点保留运行时报告和收据职责；真正阻止危险图
入队的是外部编译器的哈希、schema 和有限插槽边界，不能把画布中的报告节点误称为条件执行开关。

## 编译产物与负对照

- 能力快照指纹：`d09efa515007c2c6cd93eb9b9911aaa1ad74aca69c6c8acb27aa80774f64650f`
- 编译后规范化 workflow 指纹：`997d7fb60b8d619b8a98c0afb75ed011aee9e2aafefbbab00eeaf34737b6c85e`
- 编译 artifact 文件 SHA-256：`333c431065ea3f6fa12712b354983f544608ba508772a36b179854b5df88ea57`
- 工作流节点数：49；PBR 通道数：5。
- 路径逃逸 + `class_type` 注入：拒绝。
- 受审拓扑篡改：拒绝。
- 同名节点 schema 漂移：拒绝。
- 对真实 `/object_info` 做 API 输入校验：0 个问题。

机器证据位于 `artifacts/goal/m8-s1-pbr-compiler/`；四类 JSON Schema 位于 `contracts/`。聚焦单测
为 5/5 通过，完整 quick gate 为 119/119 通过，目标状态 revision 35 审计通过。

## 能力边界与下一步

本切片证明 Agent 能够从真实运行时能力出发，选择并编译一个受审 PBR 画布，而不是动态生成任意
ComfyUI JSON。它尚未证明模型质量、五个输出文件的语义正确性、GPU 成本、生成恢复、UE 贴图导入
或 Material Instance。M8-S2 将运行真实图，逐通道验证尺寸、色彩空间、统计量、哈希和来源，再只在
候选关卡创建材质实例、回渲和对账。
