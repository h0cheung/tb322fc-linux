# Freedom / Arch 原生 ARM64 CI（v2）

2026-10-24 起，主流水线改为 `Build Freedom Arch packages`，运行于
`ubuntu-24.04-arm`，在经过 SHA256 或签名验证的 Arch Linux Ports AArch64 bootstrap 内原生编译。
Linux 使用 `ARCH=arm64 LLVM=1`，不设置交叉编译器；内核、headers、ALS-DKMS 和 kShim 均从固定来源构建。
旧版 `scripts/build-boot.sh` 是保留的直接启动构建入口，不是新版 CI 或更新器的交付路径。

## 输入

- `FIRMWARE_URL` secret 与 `FIRMWARE_SHA256` variable（也支持 workflow 手动输入）：
  按 `firmware.json` 清单打包的四代设备固件；私有 URL 不写入构建元数据。
- `arch_rootfs_url`：Arch Linux Ports AArch64 bootstrap；可给 `arch_rootfs_sha256`，否则验证其签名。
- `rootfs_size` 默认20G，仅用于内部 rootfs 构建检查，不作为可独立刷写的发行镜像。

固件打包入口：

```sh
python3 scripts/ci/firmware-bundle.py verify inputs/firmware
python3 scripts/ci/firmware-bundle.py pack inputs/firmware build/firmware.tar.gz
sha256sum build/firmware.tar.gz
```

流水线只 fetch `sources.json` 中的 hexagonrpc、libssc、libcamera、audio topology 和 Freedom 固定提交。
内核来源、Freedom 补丁与板级树由 `packages/linux-freedom/PKGBUILD` 引用；
kShim runtime、依赖、原生打包器与 BusyBox 由 `packages/kshim-freedom/PKGBUILD` 引用构建。
来自 Freedom 的完整源码不复制进本仓库。本地差异单独保存为配置片段和补丁。

`configure-rootfs.sh` 创建构建用户后调用 `scripts/ci/build-kernel.sh`，先构建安装内核与headers，
再安装ALS-DKMS和kShim。普通设备包随后构建。CI没有本机AVB私钥和原厂boot配置，
因此安装钩子不会在runner写任何boot分区；只输出可供已初始化设备使用的软件包。
内核包的原生headers工具与DKMS模块需通过构建检查。

构建根安装 ccache，并通过 makepkg 的 `BUILDENV+=(ccache)` 启用官方编译器包装路径。
因此 `LLVM=1` 选中的 clang 也经过 ccache，无需修改内核源码或设置交叉编译器；
这与[内核 LLVM 构建文档](https://docs.kernel.org/kbuild/llvm.html#ccache)的缓存方式兼容。
缓存目录为 `/var/cache/tb322fc-build/ccache`，最大4G，按编译器内容校验；
内核使用固定构建目录，避免每轮随机路径破坏调试信息的缓存命中。
CI bind 挂载整个构建缓存并在失败时也保存，key包含run ID，下一轮按源码key或ARM64前缀恢复。
编译缓存会检查实际输入；Meson安装树另按发行版依赖版本戳失效，不沿用旧ABI。
`artifacts/ccache.txt` 记录实际命中/未命中统计；ccache不缓存链接、BTF生成或打包工作。

## Release 结构与旧更新器边界

版本 tag：`freedom-v2-YYYYmmddHHMMSS`。release 包含：

- `freedom-release.json`：format、设备、架构、内核release/build ID和四个包的版本/大小/SHA256。
- `linux-freedom`、`linux-freedom-headers`、`als-bridge-dkms`、`kshim-freedom` 四个 Arch 包。
- `SHA256SUMS`。

先在本地校验完整集合，再以 draft 上传，全部成功后发布。不会发布旧名的
`boot.img.zst`、`kernel-modules.tar.gz`，也不会复用旧 `v[0-9]` tag。
旧更新器按这些旧tag和旧资产名识别内核，因此看不到新内核更新；真实旧脚本的模拟测试覆盖此边界。

用户态滚动仓库改为 `repository-freedom-v2`。发布脚本拒绝覆盖旧 `repository`，
且不把上述四个启动包放进滚动仓库，避免普通 `pacman -Syu` 或旧脚本只更新部分启动组件。
旧仓库保留在自己的兼容范围内；不会用新版内容覆盖它。

第一次构建前，`scripts/ci/init-repo.sh` 用 `repo-add` 生成空的Arch仓库，
以draft上传 `.db`/`.db.tar.gz`/`.files`/`.files.tar.gz` 四个实体文件后才公开release。
已有完整仓库不重置，已有不完整release或认证错误会停止，不能把请求失败误当作空库。
chroot随后读取这一真实release数据库，不再临时伪造空库。四个启动包仍只进入版本release。

内部验证rootfs不写死设备根分区标签或ext4类型；真实启动由本机kShim配置中的root PARTUUID
和initramfs文件系统探测决定。内部ext4镜像仍仅用于构建检查，不作为发行资产。

首次安装或旧版直接启动系统迁移需要单独完成本机引导初始化与启动验证。
这版不发布可独立刷入的 boot/rootfs 组合，不能把 CI 内部 rootfs 当作完整安装镜像。

## 新更新器

`steamos-update` 调用 `tb322fc-update`，后者使用共享v2协议检查器。
旧系统缺少已经验证的 Freedom 包、root PARTUUID、原厂boot模板、本机AVB密钥或部署配置时，
在写入之前退出，不自动执行引导迁移。

已初始化设备的更新顺序：

1. 获取完整manifest，下载并校验四个包及其 `.PKGINFO`。
2. 备份运行内核模块与boot_a，并校验备份。
3. 建立只含该release四个包的临时本地pacman仓库，在一次系统事务中明确请求四包。
4. DKMS完成后，由kShim钩子打包对应内核、DTB、initramfs，签名并回读boot_a。
5. 核对本次新生成的成功记录、内核build ID、boot回读哈希及四包版本，最后记录已安装release。

事务或部署验证失败时，恢复原boot和运行内核模块。包数据库可能已提交新版本，
失败日志会明确提示需要修复包状态；不会把旧成功记录当成本轮成功。
更新器不会自动重启；成功后由用户重启验证。

## 检查与验证范围

```sh
python3 scripts/check.py
sudo python3 -m unittest discover -s tests -p 'test_freedom*.py' -v
```

安全回归覆盖：缺包、headers不匹配、下载损坏、旧成功记录、旧脚本读取新release、禁止覆盖旧滚动仓库。
完整GitHub CI和新产物的实际启动仍需单独执行；语法/模拟检查不代表整轮远程CI或新内核启动已通过。
