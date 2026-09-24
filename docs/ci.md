# 四代 Arch Linux ARM 镜像 CI

目标设备是 **Y700 四代 / TB322FC / elden / SM8750**。构建产物为直接启动
Linux 的 Android v4 `boot.img` 和带 KDE Plasma 的 ext4 `rootfs.img`。
这里保留四代作者已测试的启动设计，没有移植三代的 UEFI 或 GRUB。

**当前验证范围：这是新增的构建流水线，不是已实机验证的镜像发行版。**
脚本检查和固件包测试不能代替完整镜像构建与 TB322FC 实机测试。
仓库没有原厂固件，所以必须先提供下面的输入才能运行完整构建。

## 对照三代后的取舍

| 环节 | 三代参考项目 | 本仓库四代 CI |
| --- | --- | --- |
| 启动 | 已有 UEFI `boot.img` + GRUB FAT 模板 | 从源码生成 Android v4 `boot.img`，直接启动内核 |
| 内核 | 下载已编译 Image、DTB 和模块 | 从本人的 kernel fork 精确提交构建 Image、DTB、模块 |
| 设备树 | SM8650 / TB321FU | 内嵌 SM8750 / elden DTB |
| 根分区 | `PARTLABEL=userdata` | 保留 `PARTLABEL=rootfs`，不访问 Android userdata |
| 用户空间 | Arch + 从第三方 deb 中提取设备文件 | Arch + 原生编译四代 hexagonrpc、libssc、iio-sensor-proxy、libcamera |
| 固件 | 三代预置硬件包 | 用户提供四代固件；78 个文件逐一验证 SHA256 |
| 传感器校准 | 三代集成方式 | 用户在装机后导入自己的 persist 数据 |

参考代码：
[三代 Arch CI](https://github.com/GUF296/arch-y700-build-ci)、
[三代 Ubuntu CI](https://github.com/GUF296/ubuntu-y700-build-ci)。
三代构建本身依赖预编译模板和设备包，不能只换 DTB 文件名就用于四代。

`sources.json` 的 kernel URL 已指向
[tb322fc-linux-kernel](https://github.com/h0cheung/tb322fc-linux-kernel)，
内核更新为 2026-09-24 核对的 `v7.2-elden` 最新提交
`ba28ec16f01f59ba8f5099e8af9e95b061fc5c78` 及对应树哈希。仍固定具体提交，
不会在后续构建时自动追踪移动的分支。Linux 基础版本仍为 7.2，新增的是蓝牙、
背光、电池等设备补丁；原有实机验证记录不适用于这次更新。
不需要给 kernel 仓库再加一套 CI，也不需要制作 deb。

启动方式、DTB、`PARTLABEL=rootfs` 和 ext4 配置保持原设计。新加入的
`android-userdata.config` 等可选配置片段不会自动合并。
新版蓝牙冷启动还需要 `qca/brhperifw20.tlv`、`qca/brhperinv20.bin` 和
`qca/tmel_peach_20.elf`；当前 78 文件固件包没有这些文件，不能视为新版蓝牙的
完整固件集。需要取得匹配的原厂文件及真实哈希后补充清单和 initramfs，
才能验证蓝牙初始化；其他启动流程不依赖蓝牙成功。

## 1. 准备一次性固件输入

先依照[固件文档](firmware.md)从匹配的 Android 系统提取文件，并生成音频
topology、导入 regulatory database，得到完整的 `inputs/firmware/`。
它必须包含 `firmware.json` 中的全部 78 个文件。

音频 topology 编译器版本会影响二进制哈希。上游验证的是 alsatplg 1.2.15.2；
如果自己生成的 topology 不匹配，先检查工具版本，不能通过修改哈希跳过验证。
CI 直接使用经过验证的完整固件包，因此不依赖 Ubuntu 自带的 topology 编译器。

```sh
mkdir -p build
python3 scripts/ci/firmware-bundle.py verify inputs/firmware
python3 scripts/ci/firmware-bundle.py pack inputs/firmware build/firmware.tar.gz
sha256sum build/firmware.tar.gz
```

`pack` 只收录清单内的固件文件，不收录账户、Wi-Fi 密码、设备日志或单机传感器
校准数据。归档中的路径直接从 `awinic/`、`qcom/` 等开始，没有外层 `firmware/`
目录；不要用包含整个 Android 目录的随意 tar 包代替。

将这个包放在 GitHub runner 可访问的 HTTPS 地址。支持带有效期的签名下载 URL；
不要在公开工作流输入中填含凭证的 URL，改用 Actions secret。
最终 `boot.img` / `rootfs.img` 会包含这些固件，构建脚本只上传 Actions artifact，
不会自动创建公开 Release。

在 `h0cheung/tb322fc-linux` 的 Settings → Secrets and variables → Actions 配置：

| 类型 | 名称 | 内容 |
| --- | --- | --- |
| Secret | `FIRMWARE_URL` | 完整固件包的 HTTPS 下载地址 |
| Variable | `FIRMWARE_SHA256` | 固件包 SHA256，64 位十六进制 |

也可用手动运行时的 `firmware_url` 和 `firmware_sha256`。URL 优先使用 secret，
SHA256 优先使用手动输入。下载器和构建元数据不会主动记录 URL。

## 2. 运行 Actions

选择 **Build Arch Linux ARM images → Run workflow**。

| 输入 | 默认值 / 含义 |
| --- | --- |
| `firmware_url` | 留空使用 secret |
| `firmware_sha256` | 留空使用 repository variable |
| `arch_rootfs_url` | 官方 generic AArch64 rootfs |
| `arch_rootfs_sha256` | 留空时校验官方 `.sig`；指定时固定归档 SHA256 |
| `rootfs_size` | `12G`；必须不大于已准备的目标分区 |

工作流使用原生 `ubuntu-24.04-arm`，在 chroot 内编译 AArch64 设备用户空间。
流程为：固件校验 → 精确源码与补丁树校验 → Arch 基础包认证 → 内核及模块编译 →
Arch 包安装与设备服务编译 → ext4 镜像制作及检查 → zstd 压缩。

Arch 下载签名使用[官方公布的密钥](https://archlinuxarm.org/about/downloads)
`68B3537F39A313B3E574D06777193F152BDBE6A6`。默认 rootfs 和软件仓库是滚动的；
源码固定不等于整个用户空间可逐字节复现。产物记录归档 SHA256、内核配置、
源码版本与完整 pacman 包清单，方便定位变化。Mesa 不满足设备要求时应修复
软件源或等待仓库同步，不应把构建失败当作已可运行的桌面镜像。

`Check build scripts` 在 push / pull request 上独立运行，不需要固件。
它验证脚本和归档处理，成功不表示镜像已构建或设备已启动。

## 3. 下载与启动

成功后下载 `tb322fc-arch-<run-id>` artifact。主要文件：

- `boot.img.zst`：内嵌 DTB、initramfs、早期固件的直接启动镜像。
- `rootfs.img.zst`：独立 ext4 文件系统，包含 Plasma、设备用户空间和匹配模块。
- `SHA256SUMS` / `RAW-SHA256SUMS`：下载文件和解压后原始镜像的校验。
- `BUILD-INFO.txt`、`sources.json`、`firmware.json`、`kernel.config`、`rootfs.packages`：构建记录。

大于 1.9 GB 的压缩文件自动切片为 `.000`、`.001` 等，先按顺序合并。
下例合并步骤只对实际被切片的文件执行：

```sh
sha256sum -c SHA256SUMS
cat rootfs.img.zst.[0-9][0-9][0-9] > rootfs.img.zst
zstd -d boot.img.zst
zstd -d rootfs.img.zst
sha256sum -c RAW-SHA256SUMS
```

启动前需要已经解锁、且有正确准备的 **GPT 分区名 `rootfs`** 的设备；文件系统
label 也叫 rootfs 并不能替代 GPT 分区名。镜像不会替你创建分区或覆盖 Android。
必须先把 rootfs 镜像内容部署到该分区，只有 `fastboot boot` 不会安装根文件系统。
分区大小、备份和部署方法需按设备现状确认；不要把它写到 `userdata` 或其他
Android 分区。原始 ext4 镜像不是整盘 GPT 镜像，也不是 Android sparse image。

在已经完成 rootfs 部署并进入 fastboot 后临时启动：

```sh
fastboot boot boot.img
```

保留原有可用启动镜像。该路径不依赖 GRUB、EFI 分区或单独加载 DTB，
也不提供刷写 boot 分区的命令。初次验证准备 USB 键盘，以便处理首次登录和终端。

默认用户为 `alarm`，初始密码 `alarm`，首次登录必须修改。root 账户锁定，SSH
默认关闭；登录后可自行启用。网络通过 NetworkManager 配置。
Plasma Keyboard 已安装并设为 KWin 的屏幕键盘；首次密码修改仍建议用 USB 键盘。

四个设备用户空间组件目前从固定源码安装，pacman 的 `IgnorePkg` 防止发行版的
同名软件包覆盖补丁。更新这些组件时需一起更新源码清单并重新构建；不要直接移除
该保护后升级成未经验证的发行版组件。

传感器服务的二进制已经安装，但需按照[设备用户空间文档](rootfs.md#sensors-data-and-services)
导入本机的 `/var/lib/hexagonrpc` 数据后才能工作。不要把其他设备的校准数据放进
通用 rootfs；也不要让 Linux 写 Android persist。

## 本地运行

需要有 chroot/mount 权限的 AArch64 Linux 构建机，依赖列表见工作流。
除内核/BusyBox 可交叉编译外，这套 rootfs 脚本要求原生 AArch64，不会隐式启用 QEMU。
源码、输入和构建目录默认要求全新状态，避免复用旧产物冒充成功。

```sh
python3 scripts/fetch-sources.py
python3 scripts/ci/firmware-bundle.py verify inputs/firmware
bash scripts/ci/fetch-arch.sh
JOBS=4 bash scripts/ci/build-kernel.sh
sudo env ARCH_ROOTFS_ARCHIVE="$PWD/build/ArchLinuxARM-aarch64.tar.gz" \
    ARCH_ROOTFS_SHA256="$(cut -d ' ' -f 1 build/ArchLinuxARM-aarch64.sha256)" \
    ROOTFS_SIZE=12G JOBS=4 bash scripts/ci/build-rootfs.sh
```

本地归档 `package.sh` 另需 `artifacts/firmware-input.txt`，由 CI 输入步骤生成；
直接使用本地固件时可以记录自己打包的 SHA256 后再归档。

## 实机验证边界

先验证启动进入 Plasma、触控、Wi-Fi、GPU 渲染、扬声器及 rootfs 可写；再导入本机
校准并验证传感器/摄像头。CI 无法验证 UFS 时序、显示初始化、固件兼容性、
电池报告和 suspend。已有硬件限制见[支持矩阵](hardware.md)，新增 CI 不会
自动解决蓝牙发现、休眠和充电方面的限制。
