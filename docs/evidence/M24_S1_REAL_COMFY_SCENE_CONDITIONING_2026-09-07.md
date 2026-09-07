# M24-S1 · 真实 ComfyUI 场景条件生成

ArtFlow 在项目自有的 `127.0.0.1:8190` 隔离宿主中重新发现 ComfyUI 0.28.0、RTX 4080、826 个节点和 `ComfyUI-Production-Nodes` 的三个生产节点。当前模型目录没有 ControlNet 或 LoRA 权重，因此本切片没有下载新模型或虚构 ControlNet 能力，而是选择已安装 FLUX.2 Klein 的 `ReferenceLatent` 固定工作流。

| Unreal 场景条件 | 真实生成候选 |
| --- | --- |
| ![同机位 Beauty 与归一化 Depth 合成条件](../../artifacts/goal/m24-s1-scene-conditioning/scene-conditioning.png) | ![暖色穿透光候选](../../artifacts/goal/m24-s1-scene-conditioning/depth-guided-candidate.png) |

类型化 `artflow-scene-conditioning-request/1` 同时绑定 Scene Package、Beauty、原始浮点 Depth、归一化条件图、固定能力、固定 recipe、seed、denoise、尺寸和下游消费者。模型只能填写这些插槽，不能提交 workflow JSON、节点、模型路径或输出路径。

第一次实跑证明 ComfyUI `LoadImage` 会把 UE 浮点 EXR Depth 误读为纯红图；第二次直接归一化时又被 UE 的约 `1e13` 无穷远哨兵值压成二值轮廓。最终固定 Blender 预处理器排除无穷远值，以 `728.202–4166.533` 的有效深度范围归一化，并将 Depth 与同机位 Beauty 合成为颜色/结构条件。只重跑了失败的图像条件分支。

| 项目 | 真实结果 |
| --- | --- |
| ComfyUI / GPU | 0.28.0 / NVIDIA GeForce RTX 4080 |
| 节点发现 | 826；Production Nodes 3 / 3 可见 |
| 模型路线 | FLUX.2 Klein 4B FP8 + Qwen 3 4B + fixed VAE |
| 固定工作流 | 18 节点；SHA-256 `28ffe27436be1db2850d27156a28675c448085b558243e725b474b7908b8b824` |
| 真实请求 | `538f7cdf-2487-42b7-87c6-b8ad4d4c5210` |
| 输出 | 1024×576；SHA-256 `0f65a7a7bb0f1bdd0bdf9ab41e2b9e3367d0c6a15be364a5b3b9e8ccc9ff41cb` |
| 执行时间 | 9.41 秒（ComfyUI execution_start → execution_success） |
| 相对条件图变化 | 平均绝对 RGB 差 26.968 |
| 下游消费者 | `unreal.visual_target` |

宿主由 ArtFlow 启动并按记录 PID 关闭；共享 8188 端口和 ComfyUI 安装、模型目录、个人 workflow 均未修改。
