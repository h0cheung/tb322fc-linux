# Classic 与 LSFG 2.0 运行库

两份 ARM64 `.so` 原样取自 [SteamOS-ARM-Port](https://github.com/hashtagbasit/SteamOS-ARM-Port/tree/e54dac93afccf76e5fefe998399b6c1b1a23f3a1/sm8650-overlay/usr/lib)。Classic 来源为 hashtagbasit/lsfg-vk-arm64 v1.0，包含其 Proton ARM64 多实例修复；2.0 对应上游 `2333707d55b68ddd8066fd95404c3b7d07e00d3a`。打包禁用 strip，安装库保持下载时的 SHA256。原始许可证随包安装。

本包还从相同 2.0 上游提交编译 ARM64 原生 `lsfg-vk-cli`，供 Decky 的配置校验使用；不修改 2.0 库源码或二进制。插件的 x86/32 位库原始压缩包另存于 `/usr/share/lsfg-vk/payloads/`，由相应插件安装到用户目录。

Classic 使用独立 layer 名称和 `LSFG_CLASSIC=1` 开关；2.0 使用 `DISABLE_LSFGVK` 开关。Classic 启动器由插件生成在 `~/lsfg-classic`，可用 `~/lsfg-classic %command%`；2.0 配置按 Steam App ID 选择，可显式使用 `lsfg-v2 %command%`。两种启动器应分别使用。

两版 DLL 不同：Classic 使用用户购买的 `Lossless.dll`；2.0 使用 Lossless Scaling 的 `lsfg-vk` 测试分支中的 `lsfg-vk.dll`。DLL 不随包分发。切换 Steam 分支前保存 Classic 的 DLL，并在 Classic 插件中指定它的路径。

配置、Decky 接口和逐项实测由 `decky-lsfg-plugins` 包与设备文档记录。安装库不代表所有游戏都能正确插帧，也不代表某版在本设备上更快。
