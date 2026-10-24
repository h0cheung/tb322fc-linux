# Freedom 兼容改动

固定上游与配置见 `configs/freedom-sources.json`。`0001` 是 Freedom 配置片段的等价补丁，不是要应用到 Linux 驱动树的补丁。

`0002` 在全部作者补丁（含 0188）之后应用到 Linux 树，仅将现有 WCN7860 分段扫描的机型条件从 Baldur 扩展到 Elden，保留其硬件条件。2026-10-24 实机同镜像对照：原驱动首次 1493 秒联网、复测约209秒关机前未关联；扩展后临时启动5.63秒、持久A启动5.46秒联网。关联后的全信道扫描25.42秒通过，比原驱动热态11.88秒慢；单信道0.46秒通过。不据两次启动证明长期稳定性。

Landlock 已在正式兼容配置中补齐；Image、模块与 headers 必须来自同一次构建。

Q6V5 handover 单次 IRQ 修复从 Linux 主线固定提交直接引用，见 [内核配方](../../packages/linux-freedom/PKGBUILD)。本地仅保存 [attach 适配补丁](../../packages/linux-freedom/q6v5-attach-keep-handover-masked.patch)，避免 Freedom 的 Baldur 分支绕过 IRQ 状态跟踪。其他旧内核候选保持不动。

`0003` 将 Freedom 0192 的主机掉电跟踪和 xHCI 恢复通知扩展到四代 Elden。只扩展三个机型条件，保留其原有的核心掉电判断；用于验证长时间休眠恢复后的 USB DMA 地址翻译错误、Host System Error 和手柄无法重新枚举。其余五代条件单独评估。
