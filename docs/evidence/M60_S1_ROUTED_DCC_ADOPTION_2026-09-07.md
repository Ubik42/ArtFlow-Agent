# M60-S1 · 自动选路候选评价与采用

当前 Scene Session 选出的风场旗帜路线已经接入同一 append-only 事件账本、Reducer、Codex 采用决策和版本发布器。评价输入同时锁定路线决策、DCC 工作、ComfyUI / Blender / Unreal 回执、候选关卡字节和候选预览，不再借用旧 PCG / 灯光候选的评价身份。

## 评价与采用

- 评价记录：`dcc-evaluation-181f20992cd1`
- 技术检查：6/6 通过
  - 路线与三宿主回执身份
  - 当前 Session 隔离目录
  - 上游候选不变
  - 几何预算 3,948/5,000 三角面
  - 1 个材质槽与 1 个凸碰撞体
  - 1,280×720 Unreal 预览内容
- Codex 视觉判断：4/4 通过
  - 材质方向
  - 轮廓可读性
  - 场景挂接关系
  - 生产可用性
- 采用决定：`scene-adoption-4f5d61aacbeaede7`
- 内容身份：`c7a243e05e28d2163e423c4833649169b2f77f4eb9ef6fb11a877025555d9958`
- 版本目标：`/Game/ArtFlow/Published/AF_dc31f6ed0f4e/V_c7a243e05e28`
- 路线事件：7 个
- 重复评价与采用：保持相同身份
- Reducer 重放：投影等价
- 重复外部副作用：0

## 产品界面

场景变更谱把“材质意图选路 → 三宿主生成 → 六项交付检查 → 四项视觉判断 → Codex 采用 → 发布请求”呈现为一条连续生产路线。新 DCC 工作入队时，Reducer 会清除旧候选的评价、采用与发布投影，防止界面或 Publisher 引用过期结果。

- 1600 × 1000：失败图片 0；横向溢出 0
- 980 × 1200：失败图片 0；横向溢出 0
- 浏览器控制台：错误 0；警告 0

## 证据

- `artifacts/goal/m60-s1-routed-dcc-adoption/routed-dcc-adoption-receipt.json`
- `artifacts/goal/m60-s1-routed-dcc-adoption/codex-visual-observation.json`
- `artifacts/goal/m60-s1-routed-dcc-adoption/routed-dcc-adoption-desktop.png`
- `artifacts/goal/m60-s1-routed-dcc-adoption/routed-dcc-adoption-narrow.png`
- `scripts/capture_m60_routed_dcc_adoption.py`
