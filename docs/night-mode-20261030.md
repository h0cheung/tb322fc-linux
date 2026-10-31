# DPU 夜间模式在休眠后失效：复现与修复

2026-10-30 在 Y700 Gen4、`7.2.6-21-freedom` 上受控复现，并安装
`gamescope-armada 3.16.31.ogc1-6` 验证。修复位于本地
[0043 补丁](../packages/gamescope-armada/0043-drm-restore-colorops-when-reenabling-plane-pipeline.patch)，
没有重新构建或刷写内核。

## 原因

夜间模式的配置仍然开启，但 DPU 色彩管线的状态已经丢失：plane 选择了
`COLOR_PIPELINE=73/94`，对应的四个 colorop 却是 `BYPASS=1, DATA=0`。
按 Home 弹出菜单触发 GPU 合成，GPU 中的夜间色温处理仍有效，因而只有菜单出现时变暖。

现有内核的 `drm_atomic_helper_duplicate_state()` 仅在 plane 选择了色彩管线时保存
该 plane 的 colorop；恢复时 `drm_mode_config_reset()` 会重置所有 colorop。
因此，在 GPU 合成状态下休眠，原本配置好但已停用的 DPU 色彩表会被清空。

Gamescope 的 `CDRMAtomicProperty` 仍缓存着旧的 DATA 和 BYPASS 值，
`SetPendingValue(..., false)` 会跳过它认为没有变化的属性。
切回 DPU 后只重新选择了管线，没有恢复其中的色彩表。
15 秒定时休眠即可复现，不需要整夜休眠。

## 改动

`drm_set_plane_luts()` 在色彩管线从停用变为启用时，强制下发该管线的
IGC/3D LUT 数据及两个 BYPASS 属性。判断依据是上次成功提交的管线值
`GetCurrentValue()`；不能使用 pending 值，因为 liftoff 每帧做图层分配测试时
都会临时清零 pending 管线。

这样正常连续显示仍沿用属性缓存；失败后回滚、下一次重试仍会补齐属性。
这是 Gamescope 对现有内核恢复行为的兼容修复，内核本身的 inactive colorop
保存逻辑没有改变。

## 验证

同一设备、内核、夜间模式设置和 165 Hz 屏幕模式；旧版为 pkgrel 5，新版为 pkgrel 6。
每次休眠均使用 RTC 15 秒自动唤醒，并确认 suspend success 计数加一、boot ID 未改变。

| 操作 | 旧版 | 新版 |
|---|---|---|
| 单纯灭屏再点亮 | 色彩表正常 | 色彩表正常 |
| DPU 显示状态下休眠恢复 | 色彩表正常 | 色彩表正常 |
| 强制 GPU 合成、休眠恢复、再撤销强制合成 | 四个 colorop 全部丢失，切回 DPU 后仍未恢复 | 切回 DPU 时四个 colorop 自动恢复 |

新版测试过程中没有使用 `GAMESCOPE_DISPLAY_MODE_NUDGE` 手动刷新缓存。
最终 `GAMESCOPE_COMPOSITE_FORCE=0`，夜间模式属性保持启用；两个显示 plane 均为
rotation=8，四个 colorop 均 `BYPASS=0` 且持有有效 LUT。
恢复后的 5 秒采样完成 315 次呈现，Gamescope GPU submit 为 0，确认保留 DPU 显示。
这个数值是显示更新计数，不代表游戏帧率或整机功耗。

构建与自动回归结果：

- ARM64 原生增量编译、打包成功，148 项 Meson 测试及现有 33 项 Python 回归通过。
- 新测试编译实际的 LUT 提交函数和属性缓存方法，覆盖首次启用、连续显示、换表、
  不受色彩管理的图层、未分配 plane、缺失 LUT、休眠恢复和失败后重试，共 8 个场景。
  旧源码在最后两个场景失败，新源码全部通过。
- 新补丁以 fuzz=0 应用后与实测源码一致，PKGBUILD 的 38 个本地源文件哈希全部核对。
- 本轮内核日志未出现 GPU translation fault、显示 underrun 或恢复超时；
  仍有改动前已存在的 Wi-Fi、USB 休眠警告。自动验证以 SDR 主界面和 DRM 状态为依据，
  游戏内实际观感另待用户确认。

## 安装及证据

已安装并重启 Steam 会话加载新二进制：

- 包：`gamescope-armada-3.16.31.ogc1-6-aarch64.pkg.tar.xz`
- SHA256：`2b1c33f66aa377c78404447f29a61d32b691460470a28f555f23db116d7270aa`
- 运行中二进制 Build ID：`7c6298799f92676c4e82e8cf4a9a534b01385fe9`
- 本地原始记录：`build/night-mode-20261030/`，重点为 `comparison.json`、
  `gpu-suspend*.json/txt`、`fixed-gpu-suspend*.json/txt`、`fixed-final-render-path.json`、
  `regression-before.log`、`package.log` 和 `kernel.log`。
- 包与验证归档：`artifacts/night-mode-20261030/`。

旧 pkgrel 5 包同时保留在本地归档目录，以及平板构建用户主目录下的
`build/freedom-sync-20261029/gamescope-armada/`。
如需回退，安装该旧包后重启 `gamescope-session-plus@steam.service`。
