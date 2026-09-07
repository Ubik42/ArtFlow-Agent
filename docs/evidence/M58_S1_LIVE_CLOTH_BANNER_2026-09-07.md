# M58-S1 · 当前 Session 布料旗帜派发

M57 的场景挂点、ComfyUI 图案、Blender 可编辑布料源和 Unreal 派生候选已经登记为当前 Scene Session 的第二十一项有限 DCC 能力。工作项继续复用既有队列、Worker、append-only 事件和 Reducer，没有增加调度器或审批层。

## 工作项

- 工作 ID：`dcc-work-3862e008ae8b`
- 工作 SHA-256：`3862e008ae8b91f359da5f214ebaba7a24b20b98b2340ea0c000605ff5d4281f`
- 登记能力：21 项
- 生命周期：5 个事件，覆盖 queued、claimed、executing、reconciling 与 succeeded
- 重复派发：同一工作身份
- Reducer 重放：投影等价
- 重复外部副作用：0
- 最终候选：`/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/ClothBanner_B_4db41b8ff0c2`

## 产品界面

场景变更谱以“挂点绑定 → 节点材质 → 布料解算 → 资产回流 → 重放对账”呈现当前路线，并直接加载 ComfyUI 图案、Blender 第 48 帧布料结果和 Unreal 候选三段真实媒体。

- 1600 × 1000：失败图片 0；横向溢出 0
- 980 × 1200：失败图片 0；横向溢出 0
- 浏览器控制台：错误 0；警告 0

## 证据

- `artifacts/goal/m58-s1-live-cloth-banner/live-cloth-banner-work-receipt.json`
- `artifacts/goal/m58-s1-live-cloth-banner/live-cloth-banner-desktop.png`
- `artifacts/goal/m58-s1-live-cloth-banner/live-cloth-banner-narrow.png`
- `scripts/capture_m58_cloth_banner_work.py`
