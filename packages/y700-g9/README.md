# G9 2026：按键、平板震动与快捷菜单

针对设备树型号 `Lenovo Legion Y700 Gen4` 和手柄 USB `3537:1136`。基础按键映射移植自 [mydanyi/armadaos-freedom](https://github.com/mydanyi/armadaos-freedom/tree/2c8c433e806e5bc0a0e7195f450af305c1bca460/system_files/usr/share/inputplumber)，上游映射又参考 [enij90/armada-tb321fu](https://github.com/enij90/armada-tb321fu/tree/62076530bf1ff34295d671016658965e54e597f1)。本移植使用发行版 InputPlumber 0.82.0，不要求 Freedom 的 0.81 共享原始输入补丁。

数据路径：G9 按键 → InputPlumber 虚拟 Steam Deck → Steam Input → 游戏；游戏的震动沿反方向交给两个 `aw86927-haptics` 平板马达。两个马达接收同一震动效果，暂不分左右声道，不代表支持任意高清触觉波形。

G9 固件可将快速双击 Home 编码为 Consumer Control 接口的 `KEY_HOMEPAGE` 脉冲，本包把它直接映射为 QuickAccess。普通 `BTN_MODE` 保留 Guide。没有固件双击脉冲的两次较慢单击仍按普通 Guide 处理；本包不额外猜测这种双击。其他 Consumer Control 按键沿用 InputPlumber 默认键盘转换。

本包不接管陀螺仪和加速度计。已有的运动传感器桥继续供原来的消费者使用。RGB 由独立的 `armada-rgb` 控制。

安装后启用 `inputplumber.service`；如需休眠/恢复联动，同时启用上游 `inputplumber-suspend.service`。主服务运行时会接管配置所匹配的原始设备，Steam 应使用虚拟 Deck。平板马达也能维持此虚拟设备的存在，因此拔下 G9 后虚拟 Deck 仍可能在线。后续重插会重新添加 G9 输入源。

回退时先停止并禁用上述两个服务，确认原始 G9 恢复，再卸载本包；RGB 可以独立保留。具体实测结论记录在设备系统文档，配置存在或 D-Bus 调用成功不等于实体按键、画面和震动已通过人工验证。
