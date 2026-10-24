# Freedom 内核与 headers 分包

这是 Arch 风格的软件包配方，保留 Freedom 设备源码，不依赖 UEFI。`linux-freedom` 安装 Image、DTB 和模块；`linux-freedom-headers` 安装同一次构建的配置、Module.symvers、BTF/vmlinux 及 AArch64 原生辅助程序。

## 从源码构建

先在系统源码仓库运行 `python scripts/sync-freedom-packaging.py`，同步共享配置、Wi-Fi 补丁和 ALS 源码的校验和。将本目录复制到 AArch64 构建环境，运行普通 `makepkg`。配方固定 Linux 7.2.6 和 Freedom commit，应用统一补丁及 Elden 扩展；本配方 release 为 `7.2.6-2-freedom`。升级通过 pkgver/pkgrel 和固定源码 commit 表达，不依赖工作目录的 dirty 标记。

## 交叉编译后原生打包

也可在 x86-64 机器完成内核编译，再导出输入：

```sh
python export-kernel-input.py --source /path/to/linux --output /path/to/out \
  --destination /path/to/kernel-input --helpers ./build-native-helpers.sh
tar --zstd -cf kernel-input.tar.zst -C /path/to kernel-input
```

内核须使用本配方的配置与 `localversion.10-pkgrel`/`localversion.20-pkgname`，并设置空的 `LOCALVERSION` 环境变量；仅关闭 LOCALVERSION_AUTO 仍可能追加 dirty。导出程序核对实际 Image 与 vmlinux build ID，并生成哈希清单。

把输入归档和配方放到 AArch64 构建环境，设置 `FREEDOM_PREBUILT_BUNDLE` 为归档绝对路径，`FREEDOM_PREBUILT_SHA256` 为完整 SHA256，再运行 `makepkg`。包在 AArch64 环境生成，fixdep、modpost、sign-file、resolve_btfids 也在那里原生编译；不会把交叉构建的 x86 程序放入 headers。

安装的 headers Makefile 默认使用 LLVM，使普通外部模块的 `make -C ... M=...` 不必额外了解内核编译器。仍允许命令行覆盖 LLVM；这项默认只放在 headers 包，不改内核运行代码。

## 安装与更新

安装内核、headers、`als-bridge-dkms` 以及 `kshim-freedom`。保留现有 `als-bridge` 用户态包。DKMS 通过标准 pacman hooks 构建模块；95-kshim-freedom hook 在其后生成 initramfs 和签名启动镜像。

kShim 声明在 `/etc/kshim-freedom/config.json`，按 pkgbase 自动找到内核版本，配置中不写死 release。当前运行时仍使用 boot_a 内嵌载荷，不会在开机时扫描 BOOT；生成新 boot.img 无需重编 kShim 核心。`deploy_boot_a` 控制生成后是否部署，默认初始化阶段先暂存验证。尾部 BOOT 不是当前启动内容的来源。

升级/移除前，60-kshim-freedom-backup hook 保存旧模块归档和 boot 镜像至 `/var/lib/kshim-freedom/rollback/<release>/`。回退时需要恢复对应模块与启动镜像，不能只恢复 boot。自动备份失败会中止软件包事务。

## Q6V5 handover 修复（pkgrel 2）

仅新增主线 `bb7c5d6f5b41d192fa81ce404e463f5d3ce70cb3` 的单次 handover IRQ 修复，按固定提交 URL 与 SHA256 引用原补丁。首次 handover 后屏蔽 IRQ；prepare 重新启用，unprepare 同步停用，避免重复通知与中断计数失衡。

`q6v5-attach-keep-handover-masked.patch` 适配 Freedom 的 Baldur attach 分支：接管已经运行的远端时未取得 proxy 资源，保持 handover 屏蔽；后续实际启动仍由 prepare 管理。依据上游 SMP2P 软件屏蔽的评审意见，来源链接保留在补丁头。Elden 的正常 start 路径使用主线修复。没有修改 AudioReach、Iris、USB、SMP2P 状态检测等其他机制。

构建与静态/模拟检查不代表新内核已经部署或完成实机验证；运行版本应通过 uname、build ID 和启动结果另行确认。

## 新版 ARM64 UAPI 与宿主工具

引用主线 `10a47fb67340bca274276faf855d7d460afd9a7a`，为 `tools/include/linux/types.h` 补齐 128 位类型，使旧内核工具可与新版 ARM64 系统头配合。补丁按固定 URL 和 SHA256 引用。完整内核构建保持 `LLVM=1`，不额外覆盖宿主编译器或预加载系统类型头；原生 headers helpers 也不再预加载系统头。
