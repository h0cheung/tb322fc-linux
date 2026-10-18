# G9 2026：按键、DS 模式震动与快捷菜单

针对设备树型号 `Lenovo Legion Y700 Gen4` 和 G9 2026 手柄。基础按键映射移植自 [mydanyi/armadaos-freedom](https://github.com/mydanyi/armadaos-freedom/tree/2c8c433e806e5bc0a0e7195f450af305c1bca460/system_files/usr/share/inputplumber)，上游映射又参考 [enij90/armada-tb321fu](https://github.com/enij90/armada-tb321fu/tree/62076530bf1ff34295d671016658965e54e597f1)。本移植使用发行版 InputPlumber 0.82.0，不要求 Freedom 的 0.81 共享原始输入补丁。

手柄按模式开关呈现两种 USB 身份，各由一个 CompositeDevice 配置接管：

| 模式 | 身份 | 配置 | 输入 | 震动 |
| --- | --- | --- | --- | --- |
| 默认（Android） | `3537:1136`（GameSir） | `05-lenovo-y700-gen4-g9-2026.yaml` | G9 专用映射（右摇杆 `ABS_Z/RZ`、扳机 `ABS_GAS/BRAKE`、十字键 `ABS_HAT0X/Y`） | 无（该身份硬件不支持 FF） |
| DS（PS5） | `054c:0ce6`（Sony 兼容，`hid-playstation`） | `06-lenovo-y700-gen4-g9-ds.yaml` | 标准 DualSense 布局，直接透传，不加映射 | 手柄自身 `FF_RUMBLE` |

**游戏震动需要 DS 模式。** 默认模式身份没有硬件 FF；2026-10-18 起平板的两个 `aw86927-haptics` 马达不再被 inputPlumber 认领（回归系统、无消费者）。原因：马达在任何模式下都存在，放进配置会让 composite 跨模式存留，且 DS 模式下游戏震动会同时打到手柄和平板马达；而 inputPlumber 0.82 没有"按条件纳入源"的能力（schema 无条件字段、D-Bus 无增删源接口、FF 广播给所有 FF 源），按模式分流只能靠切换时重启 inputplumber 的胶水，不值得维护。

数据路径：G9 按键 → InputPlumber 虚拟 Steam Deck → Steam Input → 游戏；游戏的震动沿反方向交给当前模式 composite 的源（仅 DS 模式下手柄本体）。

DS 模式的 DualSense HID 节点被标记为 `blocked`，否则 Steam 会通过 SDL/hidraw 同时枚举出物理手柄和虚拟 Deck（controller.txt 会出现第二个 `type: 054c 0ce6` 的 "PS5 Controller"），输入走两遍；隐藏只改节点权限，输入和震动仍由内核 `hid-playstation` 负责。

G9 固件可将快速双击 Home 编码为 Consumer Control 接口的 `KEY_HOMEPAGE` 脉冲，本包把它直接映射为 QuickAccess。普通 `BTN_MODE` 保留 Guide。没有固件双击脉冲的两次较慢单击仍按普通 Guide 处理；本包不额外猜测这种双击。其他 Consumer Control 按键沿用 InputPlumber 默认键盘转换。DS 模式没有这个 Consumer Control 接口，按键由手柄固件按 DualSense 方式上报。

本包不接管陀螺仪和加速度计。已有的运动传感器桥继续供原来的消费者使用。DS 模式的触摸板、运动传感器和耳机接口节点保持可见，未纳入合成设备。RGB 由独立的 `armada-rgb` 控制，它只匹配默认身份的厂商 HID 接口（`0xFF7A`），**DS 模式下无法控制 RGB**。

安装后启用 `inputplumber.service`；如需休眠/恢复联动，同时启用上游 `inputplumber-suspend.service`。主服务运行时会接管配置所匹配的原始设备，Steam 应使用虚拟 Deck。两种模式互斥，切换模式（USB 重枚举）时旧 composite 的源清空后会自行停止（`persist` 未启用），新身份按各自配置重建，无需重启 inputplumber。

回退时先停止并禁用上述服务，确认原始 G9 恢复，再卸载本包；RGB 可以独立保留。具体实测结论记录在设备系统文档，配置存在或 D-Bus 调用成功不等于实体按键、画面和震动已通过人工验证。
