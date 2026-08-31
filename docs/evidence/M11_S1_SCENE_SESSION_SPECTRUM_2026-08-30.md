# M11-S1 Scene Session 草案与场景变更谱

## 交付结果

ArtFlow 的中文工作区不再只有冻结案例浏览能力。当前 Unreal 运行现在可以输入本轮美术意图、选择
Image / Material / Asset / PCG / Lighting 域，并编译一份 `artflow-scene-session-draft/1` 草案。
草案按固定域顺序显示可执行、待补齐和实验状态，为下一步候选关卡请求提供内容身份。

## 合同边界

- 草案只读取 reducer 重建的 `AgentRunState`、Scene Package 和能力实测；
- 输入拒绝空白意图、重复域、未知域和额外字段；
- 相同场景、意图、域与能力事实得到相同 SHA-256，输入顺序不改变身份；
- 编译不追加事件、不调用 Provider、不创建 Unreal 资产；
- PCG 与 Lighting 缺少 Scene Digital Twin 时保持 guarded，图生 3D 保持 experimental；
- 浏览器只提交意图和域，不能提交宿主代码、ComfyUI graph 或自定义执行动作。

## 聚焦验证

```text
.venv\Scripts\python.exe -m pytest tests/test_web_api.py -q
9 passed

npm run build
TypeScript + Vite production build passed

Playwright 1920x1080 focused inspection
0 console errors · 0 warnings
```

界面截图：

- `artifacts/goal/m11-s1-scene-change-spectrum.png`：Scene Session 初始状态；
- `artifacts/goal/m11-s1-scene-change-spectrum-compiled.png`：编译后的五域就绪谱、计数和草案身份。

## 证据上限

本切片证明真实持久运行可以生成确定性、无副作用的 Scene Session 草案，并证明新的场景变更谱在
桌面目标尺寸下可操作。它尚未持久化 Session、创建候选暂存请求或执行新的 Unreal 场景写入；这些
属于 M11-S2 与 M12。
