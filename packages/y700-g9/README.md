# G9 2026：HID 背键、M 与震动

当前 `1.2.0-2` 配合 `inputplumber-g9-2026 >= 0.83.0-1`，为 0.14 固件的 HID 模式
映射四个背键和 M，并通过独立的厂商 HID 输出源把游戏震动送到握把。
完整配置、测试和安装说明见 [HID.md](HID.md)，驱动实现在
[inputplumber-g9-2026](../inputplumber-g9-2026/README.md)。

以下保留 1.1.0 的移植记录，其中“仅 DS 支持震动”和 HID 双击映射已被 1.2.0 取代。
`1.2.0-2` 改为依赖仅含 G9 驱动的新包；旧 udev 修复暂不纳入，断开重连行为待单独验证。

## 1.1.0 历史记录

针对设备树型号 `Lenovo Legion Y700 Gen4` 和 G9 2026 手柄。基础按键映射移植自 [mydanyi/armadaos-freedom](https://github.com/mydanyi/armadaos-freedom/tree/2c8c433e806e5bc0a0e7195f450af305c1bca460/system_files/usr/share/inputplumber)，上游映射又参考 [enij90/armada-tb321fu](https://github.com/enij90/armada-tb321fu/tree/62076530bf1ff34295d671016658965e54e597f1)。本移植使用发行版 InputPlumber 0.82.0，不要求 Freedom 的 0.81 共享原始输入补丁。

手柄按模式开关呈现两种 USB 身份，各由一个 CompositeDevice 配置接管：

| 模式 | 身份 | 配置 | 输入 | 震动 |
| --- | --- | --- | --- | --- |
| 默认（Android） | `3537:1136`（GameSir） | `05-lenovo-y700-gen4-g9-2026.yaml` | G9 专用映射（右摇杆 `ABS_Z/RZ`、扳机 `ABS_GAS/BRAKE`、十字键 `ABS_HAT0X/Y`） | 无（该身份硬件不支持 FF） |
| DS（PS5） | `054c:0ce6`（Sony 兼容，`hid-playstation`） | `06-lenovo-y700-gen4-g9-ds.yaml` + `y700_g9_ds_swap` | G9 固件将 X/Y 反报；交换 West/North，修正按键位置 | 手柄自身 `FF_RUMBLE` |

**游戏震动需要 DS 模式。** 默认模式身份没有硬件 FF；2026-10-18 起平板的两个 `aw86927-haptics` 马达不再被 inputPlumber 认领（回归系统、无消费者）。原因：马达在任何模式下都存在，放进配置会让 composite 跨模式存留，且 DS 模式下游戏震动会同时打到手柄和平板马达；而 inputPlumber 0.82 没有"按条件纳入源"的能力（schema 无条件字段、D-Bus 无增删源接口、FF 广播给所有 FF 源），按模式分流只能靠切换时重启 inputplumber 的胶水，不值得维护。

数据路径：G9 按键 → InputPlumber 虚拟 Steam Deck → Steam Input → 游戏；游戏的震动沿反方向交给当前模式 composite 的源（仅 DS 模式下手柄本体）。

DS 模式的 DualSense HID 节点被标记为 `blocked`，否则 Steam 会通过 SDL/hidraw 同时枚举出物理手柄和虚拟 Deck（controller.txt 会出现第二个 `type: 054c 0ce6` 的 "PS5 Controller"），输入走两遍；隐藏只改节点权限，输入和震动仍由内核 `hid-playstation` 负责。

`1.1.0-4` 为 DS 模式交换 BTN_WEST/BTN_NORTH；用户已确认 X/Y 正常；`1.1.0-2` 增加 `72-y700-g9-hide-physical.rules`：在 udev 首次分配用户 ACL 前，就将这只 G9 DS 模式的 hidraw 与主 gamepad evdev/js 节点保留给 root/InputPlumber。原来的动态 `blocked` 存在热插拔窗口，Steam 活动时可能抢先打开物理节点；之后改为 0000 也不会撤销已经打开的 fd。规则同时匹配精确产品名和 VID/PID，不隐藏真正的 DualSense，也不匹配平板运动桥、G9 触摸板、IMU 或耳机节点。默认 Android 模式规则未变。

安装更新后重载 udev 规则，并让这只手柄重新连接一次，以关闭 Steam 已持有的物理连接。无需重启 Steam 或 InputPlumber。静态隐藏在 InputPlumber 停止后仍生效；若要回到 Steam 直接使用物理 DS 手柄，应先卸载本包或禁用这条规则，再重载规则并重新连接手柄。

默认/Android 模式固件将快速双击 Home 编码为 Consumer Control 的 `KEY_HOMEPAGE`，映射为 QuickAccess；普通 `BTN_MODE` 保留 Guide。该模式不额外按时间猜测双击。

DS 模式没有上述 Consumer Control 接口，实机采集只得到普通 Home 脉冲。`1.1.0-3` 增加 `y700-g9-home.service`：只读匹配名称与 USB 身份的 G9 DS hidraw，识别两次短按后通过现有 InputPlumber `SendButtonChord` 发送 QuickAccess。不抓取或修改原输入，不记录轴/IMU；原单击 Guide 不延迟，双击时可能先经过正常主菜单动作。双击窗口为 450 ms，超过 350 ms 的长按或带其他按钮的组合不参与识别。服务只在 DS 身份生效；拔插会重新查找设备与 composite，不固定节点编号。识别依赖固件实际发出两次 Home 脉冲，不能补回未上报的按键。

本包不接管陀螺仪和加速度计。已有的运动传感器桥继续供原来的消费者使用。G9 **没有实体触摸板**，DS 下该节点只是满足 PS5 协议的兼容接口，用户确认不会产生真实触摸数据；该节点、运动传感器和耳机节点仍可见，未纳入合成设备。RGB 由独立的 `armada-rgb` 控制，它只匹配默认身份的厂商 HID 接口（`0xFF7A`），**DS 模式下无法控制 RGB**。

安装后启用 `inputplumber.service`；如需休眠/恢复联动，同时启用上游 `inputplumber-suspend.service`。主服务运行时会接管配置所匹配的原始设备，Steam 应使用虚拟 Deck。两种模式互斥，切换模式（USB 重枚举）时旧 composite 的源清空后会自行停止（`persist` 未启用），新身份按各自配置重建，无需重启 inputplumber。

DS 双击辅助需另启用 `systemctl enable --now y700-g9-home.service`；其启停绑定 InputPlumber。停止该服务即可恢复 DS 原始 Home 行为，Android 固件双击映射不受影响。

回退时先停止并禁用上述服务，卸载本包并重载 udev 规则，再重新连接原始 G9；RGB 可以独立保留。具体实测结论记录在设备系统文档，配置存在或 D-Bus 调用成功不等于实体按键、画面和震动已通过人工验证。
