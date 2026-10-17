# Y700 四代的 G9 2026 灯效

Rust 源码、锁文件及测试取自 [mydanyi/armadaos-freedom](https://github.com/mydanyi/armadaos-freedom/tree/2c8c433e806e5bc0a0e7195f450af305c1bca460/packages/armada-rgb)，基线为 `2c8c433e806e5bc0a0e7195f450af305c1bca460`，保留上游声明的 `GPL-3.0-or-later`。G9 协议参考来源由上游注明为 [enij90/armada-tb321fu](https://github.com/enij90/armada-tb321fu/tree/62076530bf1ff34295d671016658965e54e597f1)。本移植增加 Arch 打包和四代设备的精确型号配置，保留上游其他配置与测试。

四代只新增设备树型号 `Lenovo Legion Y700 Gen4`，匹配 USB `3537:1136`。写入前还检查 HID 报告描述符中的厂商页 `0xFF7A`，避免误写同一手柄的普通输入接口。不将旧款 `3537:1134` 当作同一设备。

安装后，现有 armada-control / Decky RGB 页面通过同名命令发现并控制灯效，不依赖 InputPlumber。命令需要以 root 运行：

```bash
armada-rgb supported
armada-rgb get
armada-rgb set --color FF8000 --saturation 100 --brightness 25
armada-rgb off
armada-rgb apply
```

只有硬件写入成功后才保存 `/etc/armada/rgb.json`。`supported` 随手柄连接状态变化；`get` 读取保存的设置，不是读取硬件当前灯色。当前软件包不自动恢复插拔或休眠后的灯效，需要时运行 `apply`。上游已在五代验证颜色、亮度和开关；四代实测范围应以设备测试记录为准。

`makepkg` 的 check 阶段运行上游 Rust 单元测试和模拟 HID 集成测试，不操作真实手柄。测试环境路径可以通过上游 `ARMADA_RGB_*` 环境变量覆盖。
