# M23-S6 · Session 自有 DCC Worker

Blender 建模、ComfyUI PBR 装配、Geometry Nodes 布局和相机灯光交换现由同一个 Scene Session 工作项承载。场景变更谱先封存内容寻址的能力链，随后通过“启动本地 DCC Worker”调用产品 API；Worker 原子领取唯一写入权，按注册能力身份执行或对账，并把过程与最终 Unreal 候选写回既有 append-only 事件流。

![Session DCC Worker 完成四段能力链](../../artifacts/goal/m23-s6-dcc-worker/session-dcc-worker-ui.png)

| 项目 | 真实结果 |
| --- | --- |
| 产品动作 | `scene-dcc-work/queue` → `scene-dcc-work/start` |
| Worker | `artflow-local-blender-worker-v1` |
| 注册能力 | 建模 / ComfyUI PBR / Geometry Nodes / 镜头灯光，4 / 4 |
| 最终状态 | `succeeded`，进程重载后投影一致 |
| 事件 | 当前运行共 42 条，DCC 阶段 5 条 |
| Unreal 结果 | `/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Shot_B_e8e5f2673e75` |
| 重复外部副作用 | 0 |
| 浏览器验收 | 1600 × 1000，控制台错误 0、警告 0 |

启动接口仅监听本机，且不接收 Python、Shell、Blender executable、节点图、Unreal 地图或输出路径。Worker 从当前工作定义解析固定能力与项目自有制品；已有内容身份会进入对账路径，不重复生成、导入、建灯或创建候选关卡。
