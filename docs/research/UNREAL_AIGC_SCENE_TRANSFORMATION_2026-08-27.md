# Unreal AIGC 场景变换技术调研（2026-08-27）

## 调研结论

ArtFlow 下一阶段最有价值、也最能体现现代 Agent 工程能力的方向，不是继续包装二维生成结果，
而是把二维概念图作为视觉目标，生成可审阅、可执行、可回滚的 Unreal 场景增量。实现主线应以
UE 原生 PCG、Data Layers、Interchange 和类型化工具合同为骨架；ComfyUI、图像模型和图生 3D
模型是可替换能力，不拥有场景状态。

## Unreal 原生能力

### PCG：可参数化的布局执行面

Epic 将 PCG 定义为可扩展、可交互的程序化内容框架，覆盖资产工具、建筑、生态到世界生成。
UE 5.8 的 PCG Editor Mode 会暴露 Tool Graph 参数覆盖，`UPCGGraphInterface::SetGraphParameter`
也提供类型化参数入口。这意味着 ArtFlow 无需让模型生成任意 PCG 图：技术美术先制作少量经过
审阅的图，Agent 只选择图、填写参数、种子、边界和资产集合即可。

决策：首个闭环使用固定项目 PCG 图和确定性种子；图编辑器是作者工具，不是 Agent 的运行时 API。

### Data Layers：候选场景隔离

Data Layers 用于在 World Partition 中组织、加载和卸载 Actor，适合把一次 Agent 运行的新增 Actor
与源场景分离。不是所有测试关卡都必然启用 World Partition，因此实现还需要 Level Instance 或
独立候选关卡作为后备策略。

决策：`ue.stage.create` 先探测宿主能力，优先创建专用 Data Layer；不支持时复制到项目内候选关卡。
发布是显式的 Scene Delta 合并操作，暂存不是权限审批点。

### Interchange：生成资产的导入边界

UE 5.8 Interchange 是格式无关、异步、可定制且可通过 C++、Blueprint、Python 扩展的导入/导出
框架。其管线、工厂和冲突预览比直接调用通用导入函数更适合作为 AI 资产的受控入口。

决策：图生 3D 只输出候选 GLB/USD 等文件；ArtFlow 自定义 Interchange pipeline 负责命名空间、
材质策略、比例、LOD/面数和元数据。FBX 的部分 Interchange 路径仍带实验性质，首选 glTF/GLB。

### Geometry Script：后处理工具，不是首个生成器

Geometry Script 可通过 Blueprint 和 Python 操作 `UDynamicMesh`，适合网格分析、合并、UV 检查和
程序化修整；UE 5.8 文档仍将其标为 Beta 并建议谨慎用于发布。

决策：M10 前只把它作为实验性的网格验证/修整后端，不让它阻塞 PCG 与灯光主闭环。

### Unreal Python：开发期执行器与事务

Epic 的 Python Editor API 适合资产和关卡生产自动化，并支持 `ScopedEditorTransaction`。它仅存在于
Editor，导入等操作也并非全部可撤销。

决策：近期用 Python 快速验证类型化命令；稳定后把关键场景合同下沉到 C++ Bridge。每次写入都要
有内容寻址请求、前置条件、结果收据和显式清理路线，不能只依赖 Undo。

## ComfyUI 与画布编排

ComfyUI 官方 API 的 workflow JSON 可以由外部应用提交；新 API v2 进一步强调可轮询、可恢复、
幂等提交和内容寻址资源。这支持将 ComfyUI 作为异步执行器，但不意味着 Agent 应任意构造整个画布。

推荐三层结构：

1. 技术美术维护经过审阅、版本化的子图与输出合同；
2. ArtFlow `Workflow Compiler` 根据能力 manifest 选择子图并填充类型化插槽；
3. Comfy Adapter 负责上传、提交、轮询/订阅、对账和规范化 receipt。

`ComfyUI-Production-Nodes` 当前提供八个生产节点。M8-S1 已在不修改共享安装的隔离宿主中固定其
Git commit、MIT 许可证和真实 `/object_info`，并把三个门禁/收据节点纳入项目自有 49 节点 PBR
模板；编译器逐个校验 19 个所需节点的 schema 指纹。这里已实现的是“能力探测 + 受审图编译 +
提交前失败关闭”，尚未实现真实贴图输出、端到端生成收据和 Unreal Material Instance，后者由
M8-S2 验证后才能升级能力口径。

## 图生 3D 社区能力

### TRELLIS.2

Microsoft 的 TRELLIS.2 是 4B 参数图生 3D 模型，官方仓库展示了带完整 PBR 材质的 GLB 导出、
PBR 贴图生成以及训练代码，许可证为 MIT，但依赖仍各有条款。其显存、CUDA 依赖和输出质量使它
更适合作为可选高质量 Provider，而不是产品主状态机。

### Hunyuan3D 2.1

腾讯 Hunyuan3D 2.1 提供形状与 PBR 纹理生成、模型权重和训练代码，也有异步任务接口。官方仓库
同时标明模型受腾讯混元社区/非商业许可证约束，商业或公司项目使用前必须逐项核验。

### Stable Fast 3D

Stability AI 的 Stable Fast 3D 针对单图快速网格重建，包含 UV 展开、去光照和材质参数预测，适合
低延迟候选路线。仍需单独验证模型许可、硬件和输出的 UE 可用性。

决策：统一成 `asset.mesh.generate` 合同，Provider 输出不可变候选与能力/许可证信息；没有任何一个
模型被写死进 Scene Planner。M7–M9 只用项目自有合成道具完成主闭环，M10 再加入真实图生 3D 对照。

## MCP 的正确位置

MCP 规范把 Resources 定义为上下文数据、Tools 定义为模型控制的可执行函数，并特别强调数据访问
和代码执行的安全边界。对 ArtFlow 而言，MCP 的价值是让 Codex、桌面应用或其他 Agent 宿主发现
同一份场景资源与窄工具，不是替换 durable runtime。

因此：

- Pydantic/C++ 合同是源，MCP schema 从合同生成；
- 读操作以 Resources 或只读 Tools 暴露；
- 写工具只接受 Scene Delta operation，不接受脚本字符串；
- MCP tool call 也必须进入 ArtFlow 事件日志、策略、幂等和验证流程；
- MCP Server 不保存一套平行的运行状态，不拥有发布决策。

## 推荐的分阶段验证

| 阶段 | 真实问题 | 最小证据 |
| --- | --- | --- |
| M7 | Agent 能否理解并计划真实三维场景差量 | 扩展 Scene Digital Twin、灯光/PCG dry-run、保护对象不变 |
| M8 | 可否把二维方向变为可用 PBR 材质 | 固定 Comfy 子图、贴图通道验证、UE 材质实例与同机位回渲 |
| M9 | 可否完成灯光 + PCG + 资产布局闭环 | 暂存层写入、碰撞/边界/预算检查、局部纠正、发布/丢弃 |
| M10 | 外部 Agent 与图生 3D 能否安全加入 | MCP facade、一个 GLB Provider、Interchange 验证、退化路线 |

## 主要风险

- **视觉目标不可唯一反演**：二维图无法确定遮挡后的三维结构。Planner 应优先改参数和复用资产，
  并把不确定性写进计划，不能假装恢复了“真实”三维世界。
- **生成网格不可直接生产使用**：拓扑、UV、比例、材质、碰撞和许可证都可能失败。只能作为候选。
- **PCG 图生成过度自由**：任意图会把宿主代码执行风险带回系统。只允许已审阅图和参数。
- **回渲分数诱导投机**：只优化单视角会产生镜头外错误。技术 Judge 必须检查三维空间，后续增加
  少量验证机位而非只看 beauty 图。
- **前端先于合同**：界面应等三维事件合同稳定后再重做，否则会再次对历史状态过拟合。

## 一手来源

- [Epic：Procedural Content Generation Framework](https://dev.epicgames.com/documentation/unreal-engine/procedural-content-generation-framework-in-unreal-engine)
- [Epic：PCG Editor Mode（参数覆盖）](https://dev.epicgames.com/documentation/unreal-engine/pcg-editor-mode-in-unreal-engine)
- [Epic：PCG SetGraphParameter API](https://dev.epicgames.com/documentation/unreal-engine/API/Plugins/PCG/UPCGGraphInterface/SetGraphParameter)
- [Epic：World Partition Data Layers](https://dev.epicgames.com/documentation/unreal-engine/world-partition---data-layers-in-unreal-engine)
- [Epic：Interchange 导入与管线](https://dev.epicgames.com/documentation/unreal-engine/importing-assets-using-interchange-in-unreal-engine)
- [Epic：Geometry Scripting](https://dev.epicgames.com/documentation/unreal-engine/introduction-to-geometry-scripting-in-unreal-engine)
- [Epic：Unreal Editor Python 与事务](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-the-unreal-editor-using-python)
- [MCP 2025-06-18 规范](https://modelcontextprotocol.io/specification/2025-06-18/index)
- [ComfyUI 官方 OpenAPI](https://github.com/Comfy-Org/ComfyUI/blob/master/openapi.yaml)
- [Comfy API v2 官方规范](https://github.com/Comfy-Org/docs/blob/main/openapi-v2.yaml)
- [Microsoft TRELLIS.2](https://github.com/microsoft/TRELLIS.2)
- [Tencent Hunyuan3D 2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)
- [Stability AI Stable Fast 3D](https://github.com/Stability-AI/stable-fast-3d)
