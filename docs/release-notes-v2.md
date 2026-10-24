# Freedom Arch 软件包更新（v2）

本 release 是已初始化 Freedom/kShim 设备的配套更新，不是旧版直接启动镜像。
包含 `freedom-release.json`、Linux 内核及 headers、ALS DKMS、kShim 四个 Arch 包和 SHA256。
需要运行已初始化、已配置 root PARTUUID/原厂 boot/本机 AVB 密钥的 Freedom 系统。
更新器验证完整集合后在一次 pacman 事务中安装，DKMS 完成后生成并回读匹配的 boot_a；失败时恢复原 boot 与运行内核模块。

使用新版 `steamos-update` / `tb322fc-update`，不拆开手动安装启动组件。
旧 updater 不支持 v2，不能自动迁移。此 release 不发布旧名 `boot.img.zst`、
`kernel-modules.tar.gz` 或可直接刷写的 rootfs，避免旧脚本刷入不匹配的载荷。
首次安装及旧系统迁移需要单独完成引导初始化和启动验证；不要把内部 CI rootfs 当作可独立刷入的发行镜像。

用户态滚动包位于独立的 `repository-freedom-v2`，四个启动相关包只从完整版本 release 安装，
不进入滚动软件包仓库。旧 `repository` 保持原有兼容边界。
