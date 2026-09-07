# M59-S1 · 当前意图驱动的 DCC 路线选择

当前 Scene Session 不再把所有已验证能力累积成一条伪流水线。Agent 从场景身份、原始意图和宿主就绪回执编译类型化路线决策，在风场旗帜、破损变体和机关镜头三条有限路线中选择最高语义匹配项，并只派发该路线的最短有序阶段链。

## 本次决策

- 决策 ID：`dcc-route-b38cca403ba7`
- 工作 ID：`dcc-work-4d29fa0d1a91`
- 当前意图命中：`材质`
- 选择路线：风场旗帜，5 分
- 其他就绪路线：破损变体 0 分；机关镜头 0 分
- 实际派发：3 项能力，而非累计的 21 项
- 阶段：ComfyUI 纹章材质 → Blender 布料旗帜 → Unreal 静态资产
- 生命周期：5 个事件
- 重复派发：同一工作身份
- Reducer 重放：投影等价
- 重复外部副作用：0

## 产品界面

场景变更谱直接说明意图命中、三条路线评分、选择依据和本次实际阶段，并继续呈现 ComfyUI、Blender、Unreal 三段真实宿主媒体。界面表达生产决策，而不是展示内部框架或伪进度。

- 1600 × 1000：失败图片 0；横向溢出 0
- 980 × 1200：失败图片 0；横向溢出 0
- 浏览器控制台：错误 0；警告 0

## 证据

- `artifacts/goal/m59-s1-dcc-route-selection/dcc-route-selection-receipt.json`
- `artifacts/goal/m59-s1-dcc-route-selection/dcc-route-selection-desktop.png`
- `artifacts/goal/m59-s1-dcc-route-selection/dcc-route-selection-narrow.png`
- `scripts/capture_m59_dcc_route_selection.py`
