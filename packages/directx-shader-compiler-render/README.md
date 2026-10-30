# 超分 shader 构建用 DXC

以 Kettle Linux 的 DXC `1.9.2609` 配方为基础，固定源码归档及 SHA256，使用普通 Release 参数编译 DXIL 和 SPIR-V 后端。

Arch 仓库 DXC 在本机可通过简单 shader，却在 FSR2 shader 中触发 `allocHungoffUses` 断言；因此 OptiScaler 构建依赖这个单独命名的版本。关闭旧源码的生成文件格式复核，直接使用该提交自带文件，避免新 clang-format 与旧生成文本不一致；SPIRV-Tools 编译警告不作为错误。未修改 shader 算法。

此包是构建依赖，提供并替代 `directx-shader-compiler` 命令，不是游戏运行时依赖。
