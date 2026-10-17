# Y700 的两个 LSFG Decky 插件

源自 [SteamOS-ARM-Port](https://github.com/hashtagbasit/SteamOS-ARM-Port/tree/e54dac93afccf76e5fefe998399b6c1b1a23f3a1/external-and-mods/Decky/Plug-ins/homebrew/plugins)，快照 `e54dac93afccf76e5fefe998399b6c1b1a23f3a1`：新版插件 `0.14.4`，Classic 插件 `0.12.2`。保留 Python、已构建前端、资源、元数据和 BSD 许可证；本仓库不包含 Windows DLL。

本移植修正 Classic 的用户目录、保存版 DLL 检测、WSI 开关读写与带空格的 profile 名称；新版安装器使用本机编译的同版 ARM64 CLI，并保留按 Steam App ID 的配置和 workaround 脚本。未安装仅供 x86 桌面环境使用的图形 UI。两版仍采用独立配置目录和入口。

配套移植 `fast-stop` 的进程组清理到本机 `decky-loader@.service`，防止停止后遗留插件进程。原项目的 Box64/FEX HOME drop-in 适用于其 x86 Decky，本机 Decky 与 CLI 都运行原生 ARM64，因此使用 Decky 提供的实际用户目录。

安装后执行 `sudo systemctl daemon-reload` 和 `sudo systemctl restart decky-loader@实际用户名.service`，会播种这两个插件。设置在用户目录；插件代码来自 pacman 包，Decky 重启时会从系统副本恢复。修改代码应改本包，而非仅改运行目录。

在两个插件各执行一次安装，Classic 会生成 `~/lsfg-classic`，新版会安装用户运行时。Classic 使用 `~/lsfg-classic %command%`；新版按游戏条目配置，需启动器时可用 `lsfg-v2 %command%`，其调用插件生成的 `~/.lsfg` workaround。保留已有的 Armada 启动前缀时，把这些命令放在 `%command%` 之前。

Classic 的 DLL 可单独保存为 `~/.local/share/lsfg-vk-classic/Lossless.dll`，供两个 Steam 分支切换后继续使用；新版需要测试分支中的 `lsfg-vk.dll`。默认不自动导入或覆盖旧 Odin3 插件的配置与启动器。

卸载前可备份 `~/.config/lsfg-vk*`、`~/.lsfg` 与 `~/lsfg-classic`，再卸载本包并清理其两个 Decky 运行目录；用户配置和 DLL 应按需保留。完整验证范围见中文系统文档。
