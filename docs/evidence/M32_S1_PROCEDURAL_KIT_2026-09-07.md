# M32-S1 跨宿主程序化场景装配

当前 Scene Session 已完成一条真实的 ComfyUI → Blender → Unreal 场景装配链。Agent 复用 M30
登记的 ComfyUI 视觉目标与 M28 庭院边界，编译固定 `oxidized-wayfinder` 套件请求；没有下载模型，
也没有开放任意 Blender Python 或 ComfyUI workflow。

Blender 5.2 实际生成 A/B/C 三个可编辑变体。每个变体保留 Geometry Nodes recipe、`UVMap`、
`M_AF_Stone` / `M_AF_GeneratedInlay` 双材质槽、独立 LOD1 和 box collision 元数据。基础网格分别为
116 / 160 / 124 三角面，LOD1 均为 36 三角面，满足不超过基础网格 60% 的登记策略。

![Blender 程序化 Wayfinder 套件](../../artifacts/goal/m32-s1-procedural-kit/AF_Wayfinder_Kit-preview.png)

Unreal 5.8 只导入哈希匹配的三个基础网格及其 LOD1，把九个有限点位写入由上一候选派生的新
关卡。三项 Static Mesh 均验证为 2 级 LOD 和 1 个简单碰撞体。第二次执行返回 `reconciled`，
创建 Actor 0、更新 Actor 0、重复副作用 0，`ArtFlowDemo.umap` 的 SHA-256 前后一致。

![Unreal 程序化套件候选](../../artifacts/goal/m32-s1-procedural-kit/unreal-procedural-kit-candidate.png)

请求、Blender 回执、资产清单和 Unreal 回执分别保存在同一证据目录；所有交换资产和目标图均由
SHA-256 绑定。这里的 PCG consumer 是窄的确定性点位执行能力，不接收任意 graph 或宿主代码。
