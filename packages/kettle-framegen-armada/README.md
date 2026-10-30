# Kettle Framegen 可选运行库

固定 Kettle Framegen `4e736d0`，从源码编译原生 ARM64 Vulkan layer。安装后默认不启用。使用 Decky“超分与插帧”按游戏配置；也可把 `kettle-fg` 放在已有包装器之后、`%command%` 之前。

`kettle-fg` 仅修改子进程环境，停用 Classic / 新版 LSFG，保留其他 Vulkan layer。按游戏的 WSI 绕过状态写在对应 `.launcher.json`；不会改全局环境变量。图像生成由游戏设备的计算管线完成，额外 GPU 开销和画质需按游戏判断。

上游 BSD-3-Clause 许可证随包安装。A830 图像与交换链测试的通过不等于所有 Proton 游戏均兼容。
