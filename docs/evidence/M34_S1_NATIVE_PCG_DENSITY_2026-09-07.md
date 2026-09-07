# M34-S1 场景条件驱动的 Unreal 原生 PCG

ArtFlow 将当前 Unreal Depth 与三个保护区域编译为固定的 ComfyUI 空间任务。真实本地运行由
ComfyUI 0.28.0 的 `LoadImage / ImageToMask / ThresholdMask / GrowMask / MaskComposite` 节点
生成密度蒙版；项目的 Production Nodes 同时验证工作流合同、资源上限并生成回执。输出有效覆盖率
为 29.197%，保护区泄漏为 0。

| 保护对象排除范围 | 可用于布景的密度区域 |
| --- | --- |
| ![三个场景保护区域](../../artifacts/goal/m34-s1-pcg-density/protected-exclusion-mask.png) | ![ComfyUI 输出的空间密度蒙版](../../artifacts/goal/m34-s1-pcg-density/pcg-density-mask.png) |

Agent 将蒙版投影为 12 个带位置、旋转、缩放、密度和确定性种子的类型化空间点。Unreal 5.8.1
复制项目自有的 `PCG_ArtFlowScatter` 模板图，只替换登记点集与 M32 的三种 Blender Wayfinder
网格，在新的隔离候选中由原生 `PCGCreatePoints` 与 `PCGStaticMeshSpawner` 生成 12 个实例。

![Unreal 原生 PCG 使用三种 Blender 套件完成场景装配](../../artifacts/goal/m34-s1-pcg-density/unreal-native-pcg-density-candidate.png)

第二个 Unreal 编辑器进程返回 `reconciled`。PCG 图、候选关卡和 12 个实例均复用相同内容身份，
重复外部副作用为 0；源 `ArtFlowDemo` 和上游 M32 候选的文件哈希在执行前后保持一致。
