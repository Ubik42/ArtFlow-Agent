---
name: ArtFlow Scene Director
description: 以场景变更谱为核心的 Unreal 三维场景导演工具
colors:
  void: "#07090C"
  stage: "#0D1218"
  rail: "#151C24"
  line: "#2A3642"
  text: "#F0F4F2"
  muted: "#9AA8AD"
  signal-cyan: "#73B9C1"
  director-amber: "#D59658"
  verified-lime: "#B8ED72"
  fault-coral: "#FF7770"
  planning-slate: "#8291A3"
typography:
  headline:
    fontFamily: "Bahnschrift, Aptos, Microsoft YaHei UI, sans-serif"
    fontSize: "28px"
    fontWeight: 650
    lineHeight: 1.12
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Bahnschrift, Aptos, Microsoft YaHei UI, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Aptos, Microsoft YaHei UI, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Bahnschrift, Microsoft YaHei UI, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.3
rounded:
  control: "7px"
  panel: "12px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.director-amber}"
    textColor: "{colors.void}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-secondary:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "10px 14px"
  status-verified:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.verified-lime}"
    rounded: "{rounded.control}"
    padding: "6px 9px"
---

# Design System: ArtFlow Scene Director

## Overview

**Creative North Star: “场景变更谱”**

界面借鉴调色台、混音台和虚拟制片 call sheet：场景图像占据中心，五条变更域像谱带一样呈现
强弱、依赖和就绪度。使用者先看到“哪些方面将改变、当前能不能执行”，随后再追查工具、评价和
回执。深色来自 UE 工作站的物理环境；略带纸张和氧化铜质感的琥珀/灰蓝信号形成 ArtFlow 的
识别度，不使用常见 AI 产品的紫蓝霓虹和玻璃卡片。

系统拒绝通用聊天壳、自由连线节点画布、门禁词汇主导的仪表盘、同尺寸卡片墙和伪终端英文。
界面可以有电影式空间感与光效，但业务状态必须比装饰更清楚。

**Key Characteristics:**

- 真实场景媒体是第一视觉层级。
- 横向“场景变更谱”表达多管线协作，类型化连接不可任意改线。
- 右侧决策镜头只显示可追溯摘要与证据，不显示隐藏思维链。
- 平面分区为主，运行、选中和交付时才产生提升、辉光和动效。
- 桌面高密度，窄屏切换为场景叙事顺序，而不是整体缩小。

## Colors

炭黑场景台承载一个有明确语义的完整调色板，颜色既区分管线，也形成虚拟制作现场的节奏。

### Primary

- **导演琥珀**：当前选择、主要动作和被采用路线，不能用于普通装饰。
- **信号灰蓝**：场景观测、扫描、输入事实和实时连接；饱和度保持低于场景媒体。

### Secondary

- **验证黄绿**：已验证、已对账、可发布结果。
- **计划石板灰**：计划、评价分歧和跨工具编排，不把“AI 推理”做成装饰色。

### Tertiary

- **故障珊瑚**：确定性失败、泄漏、越界和不可发布状态。

### Neutral

- **虚空黑**：应用背景和图像外的最深层。
- **舞台墨**：核心工作区。
- **轨道灰**：工具轨道、检查器和操作表面。
- **结构线**：区域分隔与关系线。
- **主文本 / 次文本**：中文正文、标签和技术元数据。

**The Evidence Color Rule.** 验证黄绿只在真实回执或确定性检查通过后出现；模型自评分不能使用它。

## Typography

**Display Font:** Bahnschrift（回退 Aptos、Microsoft YaHei UI）

**Body Font:** Aptos（回退 Microsoft YaHei UI、system-ui）

**Label/Mono Font:** Bahnschrift；ID、哈希和坐标使用系统等宽字体

**Character:** 紧凑但不微缩，数字清晰，中文自然。标题提供导演台的力度，正文负责把复杂 Agent
行为解释成人能一次读懂的句子。

### Hierarchy

- **Headline**（650，28px，1.12）：当前场景与当前运行结果。
- **Title**（600，16px，1.3）：管线、评价和候选区标题。
- **Body**（400，14px，1.6）：说明与状态解释，长文限制在 70ch 左右。
- **Label**（600，12px，1.3）：按钮、轨道和状态；中文不强制大写或扩大字距。
- **Technical**（500，11px，1.45）：哈希、版本、路径与坐标，可截断并提供完整 title。

**The Chinese First Rule.** 面向用户的状态、操作和解释必须是自然简体中文，英文只保留产品名、
协议、格式和真实技术标识符。

## Elevation

默认使用平面与色调层级。场景视口通过暗角和媒体对比形成深度；面板不使用宽软阴影。只有当前
选中候选、浮层和完成时刻可以获得短距离阴影或受控辉光。

### Shadow Vocabulary

- **选中提升**（`0 6px 8px rgba(0,0,0,.28)`）：仅用于正在比较的候选或弹出检查器。
- **信号辉光**（`0 0 18px rgba(102,220,240,.18)`）：运行中的扫描线和实时连接，不用于静态卡片。

**The Flat Console Rule.** 常驻表面保持平整；如果所有区域都在发光，整个界面即为不合格。

## Components

### Buttons

- **Shape:** 精确圆角矩形（7px），桌面高度 36–40px。
- **Primary:** 导演琥珀底、虚空黑字，只保留一个明确主动作。
- **Hover / Focus:** 亮度提升；焦点使用 2px 信号青外框，不能只靠颜色变化。
- **Secondary / Ghost:** 轨道灰或透明底，用结构线和文本明度表达层级。

### Chips

- **Style:** 小型状态片使用 6px 圆角，不使用无意义全胶囊。
- **State:** 同时显示图标或文字；实验、已验证、纠正中、失败不能只依赖颜色。

### Cards / Containers

- **Corner Style:** 主面板 12px，工具节点 6px。
- **Background:** 舞台墨与轨道灰承担常驻层级。
- **Shadow Strategy:** 默认无阴影，遵守 Flat Console Rule。
- **Border:** 1px 结构线只用于真实分区，不给每段文字套卡片。
- **Internal Padding:** 12、16、24px 三级。

### Inputs / Fields

- **Style:** 轨道灰底、1px 结构线、7px 圆角，控件标签始终可见。
- **Focus:** 2px 信号青外框。
- **Error / Disabled:** 故障珊瑚配明确中文原因；禁用状态仍保持可读。

### Navigation

顶部只保留产品、当前场景、运行状态和全局动作。场景列表在桌面为窄轨，在窄屏折叠为可横滑的
运行选择器。活动项使用导演琥珀定位标记和更高文本对比。

### Scene Change Spectrum

场景变更谱是标志性组件。Image、Material、Asset、PCG、Lighting 以五条固定谱带排列，用刻度、
短杆、纸签式说明和状态文字表达作用强度、前置条件与依赖。UE 是场景宿主，MCP 是接口边界，
不与生产域并列成“Agent 节点”。用户可以选择域和约束，但不能任意连线制造未验证工作流。

## Do's and Don'ts

### Do:

- **Do** 让真实 Unreal 画面和概念参考占据首屏最大面积。
- **Do** 用导演琥珀表示当前选择，用验证黄绿表示已通过确定性检查的事实。
- **Do** 为加载、空、失败、纠正、对账和发布提供完整中文状态。
- **Do** 在 900px 以下重排为“目标、候选、计划、评价、来源”的叙事顺序。
- **Do** 为扫描、布局变化和完成反馈提供 reduced-motion 替代。

### Don't:

- **Don't** 使用通用聊天壳、低代码流程图或自由连线的节点编辑器。
- **Don't** 让 Approval、Gate、Evidence 等治理词汇占据首屏。
- **Don't** 使用同尺寸卡片网格、伪终端英文、整页细小等宽字或霓虹边框堆叠。
- **Don't** 把计划能力写成已完成，或把二维贴片描述成三维场景修改。
- **Don't** 用渐变文字、32px 以上面板圆角、宽软阴影加细边框的幽灵卡片。
