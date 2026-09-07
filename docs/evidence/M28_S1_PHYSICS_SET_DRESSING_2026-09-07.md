# M28-S1 · Physics-assisted set dressing

本切片把 Blender 刚体求解作为受约束的场景布景能力接入 ArtFlow。

| Blender 5.2 求解预演 | Unreal 5.8 隔离候选 |
| --- | --- |
| ![12 个碎石在庭院范围内完成刚体落定](../../artifacts/goal/m28-s1-set-dressing/AF_Courtyard_SettledRubble-preview.png) | ![变换清单回填后的候选关卡](../../artifacts/goal/m28-s1-set-dressing/unreal-set-dressing-candidate.png) |

- 请求绑定当前 Session、M26 Surface 请求/回执和源 `.blend`，并固定原型 `AF_Rubble_01`、12 个实例、种子 `260907`、庭院范围和 96 帧上限。
- Blender 5.2.0 LTS 保留可编辑刚体场景，输出登记原型 GLB、12 项变换清单和同机位预览。
- 第 95→96 帧最大位移为 `0.000002 m`，实例最小中心间距为 `0.767912 m`；全部变换有限且位于登记边界内。
- Unreal 5.8.1 从 Surface 候选派生 `Dressing_B_c496854357de`，导入唯一原型并应用 12 项变换；第二次运行返回 `reconciled`，新建 Actor 数为 0。
- 源 `ArtFlowDemo.umap` 前后 SHA-256 均为 `620e4814…d24974a`，重复外部副作用为 0。
