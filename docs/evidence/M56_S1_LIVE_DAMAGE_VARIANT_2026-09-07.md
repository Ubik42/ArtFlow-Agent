# M56-S1 · 当前 Session 破损变体派发

M55 的场景条件破损路线已经登记为当前 Scene Session 的第二十项有限 DCC 能力。一次内容绑定的工作项把 ComfyUI 空间场、Blender 可编辑破损资产和 Unreal 派生候选接入既有队列、Worker、事件账本与场景变更谱，没有增加第二套调度或审批流程。

## 派发与重放

- 工作项：`dcc-work-5f9ea7700abf`
- 工作内容 SHA-256：`5f9ea7700abf54d1a7e50c71595732823584367b9fc9e9f2a0be9a9b6ddee14b`
- 登记能力数：20
- 生命周期事件：5 个，覆盖 queued、claimed、executing、reconciled 与 succeeded
- 重复派发：返回同一工作项
- Reducer 重放：投影等价
- 重复外部副作用：0

## 精确身份链

- 破损请求：`fdfe74fd21b19008d7cdeee04c435dd02298910b86ba8e39b5c0db092b8ef4bb`
- ComfyUI 回执：`5792f055f26a76508081ca8e4419860e141b85a560821b1a533c62810caf280f`
- Blender 回执：`d68ab2566adc11056d823862a590dadbeff609d07beade4a7a07e0783e5a04c1`
- Unreal 回执与最终结果：`5982ec793df6a06c93438c993a2081b6da9e0a02ff3bdb00bd4fd762fa63a6bd`
- 损伤场：`284b199301726d79bd590a8a6a1bc5f00801369258039c4f309cc973f282c168`
- GLB：`068cb8cf5bd9bf8f75cac90ed1e8a05e815dc0500af39a4d9a8105446346ec7d`
- Blender 清单：`96f0f147353449e32eb46d3f1bb5be5a8fecfbbc1be37adbaef72d9f8f501fe1`
- Unreal 候选：`/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/Damage_B_fdfe74fd21b1`

## 产品界面

桌面与 980 px 窄屏视图均加载真实 ComfyUI 损伤场、Blender 破损资产和 Unreal 候选截图。检查结果为失败媒体 0、横向溢出 0；界面直接呈现二维场如何进入可编辑 DCC 加工并成为三维引擎资产。

## 证据

- `artifacts/goal/m56-s1-live-damage-variant/live-damage-variant-work-receipt.json`
- `artifacts/goal/m56-s1-live-damage-variant/live-damage-variant-desktop.png`
- `artifacts/goal/m56-s1-live-damage-variant/live-damage-variant-narrow.png`
- `scripts/capture_m56_damage_variant_work.py`
