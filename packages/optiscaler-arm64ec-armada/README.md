# ARM64EC OptiScaler

参考 Kettle Linux `91e3b5c` 的配方，固定 Sloptiscaler 与依赖提交；Kettle 六项补丁通过固定 URL 和 SHA256 引用。构建 SGSR2、Arm ASR 与 FSR2.2，安装为按游戏复制的 PE DLL，适用于 Proton ARM64。

本包依赖 `directx-shader-compiler-render` 生成 DXIL / SPIR-V。禁止把 shader 编译失败后退回的占位实现当作完整包发布；构建会检查 ASR shader、FSR2 shader 和 ARM64EC FSR2 静态库。使用方式见 [Decky 面板](../decky-render-tools/README.md)。

安装包本身不修改游戏。用户在面板启用后才放置代理 DLL；关闭会恢复原文件。实际游戏需要可接管的 DLSS / FSR2+ / XeSS 接口，游戏内效果由用户进一步验证。

配方按构建主机选择固定版本的 AArch64 或 x86-64 LLVM-Mingw，产物均为 ARM64EC DLL。`DXC` 可指定已验证的宿主编译器路径，`OPTISCALER_JOBS` 控制 C++ 并行数（默认4）；CI 保持 AArch64 原生打包。
