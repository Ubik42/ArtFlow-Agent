# M53-S1 · Unreal 机关镜头包

## 结果

M51 的同一套骨骼机关已经进入 Unreal 5.8 Level Sequence。内容寻址请求只引用冻结的候选关卡、
Skeletal Mesh、Skeleton 与 Animation Sequence，并把可变范围限制为 48 帧机关动作、固定相机和
单个灯光提示。Unreal 在新的候选关卡内建立动画段、可生成 CineCamera、常量相机 Transform Track、
Camera Cut 与灯光绑定；没有修改 M51 源候选。

三张关键帧由 Sequencer 离屏渲染，而不是模拟 UI 或静态占位图：

- 第 1 帧：闭合起始；
- 第 24 帧：左右铰链分别达到约 -70° / +70°，通道打开；
- 第 48 帧：回到闭合状态。

## 可核验证据

- 请求：`artifacts/goal/m53-s1-mechanism-shot/mechanism-shot-request.json`
- Unreal 回执：`artifacts/goal/m53-s1-mechanism-shot/unreal-mechanism-shot-receipt.json`
- 关键帧：`unreal-mechanism-shot-closed_start.png`、`unreal-mechanism-shot-open.png`、
  `unreal-mechanism-shot-closed_end.png`
- Level Sequence：`/Game/ArtFlow/Sequences/Generated/LS_AF_MechanismShot_3273ac1a1081`
- 派生候选：`/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/MechanismShot_B_3273ac1a1081`

最终独立进程回执为 `reconciled`：新建 Actor、Package、Binding 与 Track 均为 0，重复轨道为 0；
源候选执行前后 SHA-256 均为
`07075d0f6f77a74ead6ba317d6915ab2c821eef34b22e59a835131683175b916`。

## 生产意义

这一切片不是单独的“生成一个动画”。Agent 把 Blender 中可编辑的绑定与 Action，转换成引擎内
可继续剪辑、布光和交付的镜头资产，并以内容身份保证恢复时不会重复创建关卡、轨道或绑定。
它补齐了从程序化资产制作到 Unreal 时序内容的最短闭环。
