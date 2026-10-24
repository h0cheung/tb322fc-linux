# kShim 启动交付

此包提供 AArch64 打包工具、kShim runtime、AVB 工具、F2FS initramfs 生成器和 pacman hooks。默认从固定来源原生构建；也支持显式传入 `KSHIM_TOOLS_BUNDLE` 及其 SHA256 使用已核验的工具归档。原生工具和 BusyBox 保持构建后的原字节，不再进行 makepkg strip。产物的实机验证状态需单独记录。

原厂 boot 基底与 AVB 私钥不放入软件包。设备配置 `/etc/kshim-freedom/config.json` 指定其本地路径、原厂镜像哈希、根 PARTUUID、cmdline、早期固件及 pkgbase；私钥位于 root 限权目录，权限须为 0600。部署目标固定为本项目的 Linux boot_a，拒绝其他机型或根分区不匹配的环境。

`freedom-kernel-update --kernel <release> --stage-only` 生成并校验候选，`--deploy` 在完整备份后写 A 并回读；配置 `deploy_boot_a` 可让更新 hook 自动部署。程序不重启系统，不写 B/recovery。候选、打包检查、签名和部署结果位于 `/var/lib/kshim-freedom/candidates/`，最新结果见 `latest.json`。

95 hook 在 DKMS 之后运行，要求必需模块已能由 modinfo 找到。60 pre-transaction hook 在旧模块被移除前保存模块与 boot。首次安装应先检查候选，完成真实启动验证后再启用自动部署。
