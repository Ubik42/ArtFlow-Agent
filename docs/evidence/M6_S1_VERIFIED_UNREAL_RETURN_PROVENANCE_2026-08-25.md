# M6-S1 已验证 Unreal 回流与来源链

## 结论

Codex 编排器把已采用且像素边界验证通过的第二次局部修订自主回流到项目自有 Unreal Engine 5.8 测试工程。固定 typed request 仅允许写入 `/Game/ArtFlow/Returns` 与 `/Game/ArtFlowDemo`；来源不同的资产不能占用同一确定性目标。UE 导入、资产元数据、关卡绑定 Actor 与可见截图均已完成，第 25 个主运行事件记录最终 delivery。

## 真实宿主证据

- Engine：`5.8.1-56057345+++UE5+Release-5.8`
- Imported asset：`/Game/ArtFlow/Returns/T_ArtFlow_afcf4b4e1f2a1194a8d6.T_ArtFlow_afcf4b4e1f2a1194a8d6`
- Scene：`/Game/ArtFlowDemo`
- Binding actor：`ArtFlow_Return_1194a8d6`
- UE content validation：2 个相关资产通过，0 个 Map Check 错误、0 个警告
- Return receipt：`d26b378f3756499c6ee83a6202d7f2dd169a435b80e22925dae2e9e6856c510c`

## 来源与限制

来源清单使用 C2PA 2.4 的 `claim_generator_info`、`c2pa.hash.data`、`c2pa.actions.v2` 与 `c2pa.ingredient.v3` 词汇。独立只读验证器通过 9/9 个文件绑定，来源清单哈希为 `98cbdf77c0d9b33c068f9fa15d0660675921dcb41725a9bf9780345c01591860`。

它是 `compatible_unsigned_sidecar`，不是嵌入媒体的签名 JUMBF Manifest Store。本机没有 `c2patool` 与签名证书，因此验证报告明确返回 `C2PA_SIGNATURE=not_present`，不声称完整加密 C2PA conformance。C2PA 2.4 要求标准 Claim 聚合硬绑定断言并被签名；本项目当前只证明可重放的内容哈希链与兼容映射。[C2PA 2.4 Technical Specification](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html)

## 证据入口

- `artifacts/goal/m6-s1-unreal-return/unreal-return-request.json`
- `artifacts/goal/m6-s1-unreal-return/unreal-return-receipt.json`
- `artifacts/goal/m6-s1-unreal-return/unreal-return-visible.png`
- `artifacts/goal/m6-s1-unreal-return/provenance-manifest.json`
- `artifacts/goal/m6-s1-unreal-return/independent-verification.json`
- `artifacts/goal/m6-s1-unreal-return/verified-delivery.json`
- `scripts/verify_provenance.py`
