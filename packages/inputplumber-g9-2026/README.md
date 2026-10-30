# InputPlumber：G9 2026 HID 震动

`inputplumber-g9-2026 0.83.0-1` 基于官方 `v0.83.0` /
`4ed1f50c7801e4f91fd17ce1a7b2b9d8d8b82e69`，仅增加 G9 厂商 HID 输出源。

`0001-add-legion-g9-rumble.patch` 注册驱动，`legion_g9.rs` 由 `prepare()` 安装到源码树。
原 `inputplumber-udev-fix` 的设备发现/移除补丁暂不包含；断开重连和休眠恢复仍需单独验证。

G9 驱动只接受 USB `3537:1136` 的 interface 4，并检查完整厂商报告描述符。
输入继续由普通 evdev 源处理，不需要复制按键/轴解析，不修改耳机、RGB 或内核驱动。
厂商接口以 `passthrough: true` 接入现有 composite，原来的 RGB 服务仍可打开该接口。

电机报文为 `00 04 L TL R TR SUM`，包含 hidraw 的零报告 ID。
`TL/TR=1` 表示 250 ms，零强度对应零时间，`SUM` 为命令体前五字节之和的低 8 位。
该命令已在 G9 2026 实机上验证，不需要为震动另刷固件。

驱动支持 InputPlumber 的普通 rumble、Steam Deck / DualSense 震动输出及 evdev `FF_RUMBLE`。
evdev 效果包含延迟、时长、重复、更新、删除、独立停止、叠加和全局增益；
效果槽最多 64 个，拒绝不支持的效果类型和硬件按键触发。
普通震动以 100 ms 间隔续发 250 ms 的短命令；输入源停止/析构发送零强度。
进程中断或失去设备后，固件的电机超时可以停止最后一条命令。
不将握把电机声明为触摸板或扳机触觉设备。

```sh
makepkg -s
sudo pacman -U inputplumber-g9-2026-0.83.0-1-aarch64.pkg.tar.*
```

`check()` 运行上游库/主程序测试，包括新增报文、定时和效果混合测试。
与 `y700-g9 >= 1.2.0-2` 一起安装后重启 InputPlumber。游戏仍使用原来的虚拟 Steam Deck；
新驱动作为相同 composite 的输出源接收震动，不创建额外虚拟手柄。

回退可重新安装先前的 `inputplumber-udev-fix 0.83.0-2` 与 `y700-g9 1.1.0-4`。
不要只回退 InputPlumber 并保留依赖新输出驱动的 G9 配置。

2026-10-29 的实机按键、摇杆和震动验证使用旧包 `inputplumber-udev-fix 0.83.0-3`。
驱动实现保留不变；该记录不代表移除 udev 补丁后的热插拔行为已经验证。
