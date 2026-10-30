# G9 2026 HID 配置与验证

适用于设备树型号 `Lenovo Legion Y700 Gen4`、G9 2026 `3537:1136`。
`1.2.0-2` 配合 `inputplumber-g9-2026 >= 0.83.0-1`，继续输出虚拟 Steam Deck + 键盘。
固件 0.14 增加背键、M 和 16 位 HID 摇杆上报；厂商震动命令在官方 0.10 已经存在。

参考 [enij90 的 G9 profile](https://github.com/enij90/armada-tb321fu/blob/main/system_files/usr/share/inputplumber/devices/05-lenovo-legion-g9.yaml)
和 [capability map](https://github.com/enij90/armada-tb321fu/blob/main/system_files/usr/share/inputplumber/capability_maps/lenovo_legion_g9.yaml)，
普通按键保持本仓库已有的 2026 映射。新版本使用新增按钮，不再把旧 G9 的 `BTN_C/BTN_Z`
当成独立背键；本平板的传感器桥和系统马达均不纳入此 composite。

| 输入 | InputPlumber |
|---|---|
| `BTN_MODE` | Guide，固件直接上报原始 Home |
| `BTN_TRIGGER_HAPPY1` | LeftPaddle1（物理左上） |
| `BTN_TRIGGER_HAPPY2` | RightPaddle1（物理右上） |
| `BTN_TRIGGER_HAPPY3` | LeftPaddle2（物理左下） |
| `BTN_TRIGGER_HAPPY4` | RightPaddle2（物理右下） |
| `BTN_TRIGGER_HAPPY5` | QuickAccess（M） |
| `ABS_X/Y`、`ABS_Z/RZ` | 左/右摇杆，范围由 evdev 提供，不截断到 8 位 |
| `ABS_BRAKE/GAS`、`ABS_HAT0X/Y` | 左/右扳机、方向键，沿用原映射 |

背键需在官方 App 中设置为不映射，避免普通按钮同时触发。
固件的 M 编程手势暂时保留；本轮两次点按都观察到独立按下/释放。
16 位传输字段不表示传感器有 16 位有效精度。
上述物理键序与标准 FF 通路已完成 [2026-10-29 实测](VALIDATION-20261029.md)。

`05-lenovo-y700-gen4-g9-2026.yaml` 将 evdev 游戏手柄与 interface 4 的厂商震动源
放入同一个 composite。interface 3 的原始 hidraw 和 Consumer Control 被屏蔽，
避免 Steam 读入第二份按键或执行旧的固件快捷键。
厂商接口保留 passthrough，现有 RGB 服务可继续打开它。音频不匹配到任何输入源。

震动路径：游戏/Steam Input → 虚拟 Steam Deck → InputPlumber 的 G9 输出源 → 握把电机。
厂商源只在 HID 身份存在，切换模式或拔出手柄后一起移除，不以平板常驻马达维持旧 composite。
详见 [驱动说明](../inputplumber-g9-2026/README.md)。

## 安装与检查

先构建、安装 `packages/inputplumber-g9-2026`，再构建、安装本包并重启 InputPlumber。
仓库的 rootfs 构建会按包依赖顺序构建两者。

```sh
makepkg -s
sudo pacman -U y700-g9-1.2.0-1-any.pkg.tar.*
sudo systemctl restart inputplumber.service
```

已安装的 InputPlumber 自带终端可视化面板，无需停止现有设备管理：

```sh
inputplumber device 0 test
```

其中 `0` 是本次 G9 composite 的编号；面板显示按键、摇杆和扳机状态。
按 `q` 退出并恢复测试前的配置。它展示 InputPlumber 处理后的输入；
分析固件原始坐标层级仍使用下面的 HID 采样工具。

只读诊断工具 `capture-hid.py` 读取 0.14 的 15 字节报告，显示按键与实际轴采样统计：

```sh
sudo python3 capture-hid.py --seconds 60 --log /tmp/g9-hid.jsonl
```

摇杆精度应检查实际观察到的坐标层级与步长，不以显示范围判断有效精度。
若需要独立图形界面及时间曲线，可使用
[evtest-qt](https://github.com/Grumbel/evtest-qt)。
物理 evdev 已被 InputPlumber 抓取，直接旁读它可能收不到事件；
查看游戏输出可选择虚拟手柄，检查原始 HID 则使用只读采样工具。

标准 FF 通路可用 `rumble-test.c`。明确选择 Steam/InputPlumber 的虚拟游戏手柄节点，
它上传一个 300 ms、左右约 38% 强度的 `FF_RUMBLE`，随后停止并删除：

```sh
cc -O2 -Wall -Wextra -Werror rumble-test.c -o rumble-test
./rumble-test /dev/input/eventN
```

## DS 模式与回退

DS `054c:0ce6` 仍由 `hid-playstation` 处理输入和原生震动，独立使用
`06-lenovo-y700-gen4-g9-ds.yaml` / `y700_g9_ds_swap.yaml`，保留已验证的 West/North 交换。
原始 hidraw 静态隐藏规则继续限定产品名和 USB 身份，不隐藏耳机或平板传感器桥。

此前的 `y700-g9-home.service` 是可选的 DS 双击辅助。
HID 0.14 的固件双击动作已禁用，QuickAccess 由 M 提供，HID 不依赖该服务。
可通过 `systemctl disable --now y700-g9-home.service` 停用 DS 双击辅助。

以下实机记录对应旧驱动包；去掉 udev 补丁后的重连行为尚未完成验证。

完整回退同时恢复 `inputplumber-udev-fix 0.83.0-2` 和 `y700-g9 1.1.0-4`，
并根据固件版本恢复映射。新配置的独立按键无法在原厂固件上凭空出现。
