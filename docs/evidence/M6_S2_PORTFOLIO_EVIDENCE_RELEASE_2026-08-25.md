# M6-S2 作品集证据台与可验证发布

## 结论

ArtFlow 已收口为可直接审阅的中文作品集版本。README 通过十张真实运行截图串起 Unreal 场景、双 Provider、独立 Tribunal、越界负对照、Codex 自主采用、蒙版限定修订、恢复、记忆、Harness 和 UE 回流。Scene Lab 增加最终交付面板，同时保留 unsigned C2PA sidecar 的明确限制。

## 发布证据

- 主运行：`local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb`
- 事件：25 个 append-only 事件，无待处理决策
- 发布包：`artflow-agent-portfolio-f157471a784dbe7b.zip`
- ZIP SHA-256：`ad449ba8b77180af5a5ae32fafcb10bed984d506c603d2b1af45bdfcd3446bcc`
- Manifest SHA-256：`f157471a784dbe7b7f43c21a5d486674aade0543058b4ea4a58c938de436eb0c`
- 包内文件：24/24 内容哈希通过
- Harness：20/20 冻结案例
- Recovery：6/6，重复副作用 0
- Memory：6/6 治理案例
- Provenance：9/9 文件绑定；签名状态 `not_present`

工程验证器和 ZIP 内自带的 Python 标准库验证器都重新打开原始 ZIP 并通过。篡改测试证明任一声明制品变化会导致非零退出码。

## 展示与 QA

- `docs/assets/portfolio/` 固化十张公开展示截图，不依赖被忽略的本地运行目录。
- 1440px 桌面与 390px 窄屏均无横向溢出、坏图或浏览器控制台错误。
- 窄屏完成态底栏改为普通文档流，不遮挡证据内容。
- 全量 Python 测试 101/101；Quick Gate（含脚本测试）107/107。

## 诚实边界

该版本证明一条项目自有 UE 5.8 运行的端到端工程闭环，不声称开放域质量 benchmark。C2PA sidecar 使用兼容词汇和可验证哈希，但没有 JUMBF、证书或加密签名。Harness 延迟来自冻结本地夹具，不代表外部 Provider 生产延迟。
