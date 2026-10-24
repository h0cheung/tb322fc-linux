# ALS bridge 的 DKMS 部分

本包只提供内核模块源码；现有 `als-bridge` 包继续提供 SensorProxy 守护、udev 规则和服务。内核包不再重复携带同名模块。

使用标准 DKMS/pacman hooks，针对匹配 `*-freedom` release 且已安装 headers 的内核编译。通过 LLVM 构建，生成带匹配基准 BTF 的模块。官方 linux-headers 对应另一内核，不能替代 linux-freedom-headers。

修改原 `packages/als-bridge/` 中的 C 源码后，运行 `python scripts/sync-freedom-packaging.py` 再构建本包，避免两份源码漂移。
