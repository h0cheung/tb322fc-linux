# Freedom Control 的 Arch 适配

2026-10-29 同步后，后台引用 armadaos-freedom 固定提交 `9788014a0293dc26745b000d02854ad88ef73e88` 的原始文件及 SHA256；Decky 前端引用该项目指定的 freedom-control 提交 `61a8e9631c0ba597ff0f48bc91ae766eef20bf6a`。不再内置完整 Control 源码副本。

`arch-control-compat.patch` 保留动态会话用户、Arch 的 Plasma/Mobile 会话名和本项目已有 ABL 接口。前端使用对应的用户目录补丁。新增手势开关、临时暂停手势和校准后重载接口；游戏会话启动时读取保存的手势设置。Turnip 变体只是上游可选接口，没有安装其他 Mesa 变体。

设备已安装后台、插件和会话包，Decky 成功加载 Freedom Control，查询桌面模式/手势/设备信息通过。54 项上游前端测试及4项本地兼容测试通过；游戏界面的完整操作仍待日常使用验证。

本次同步加入独立的游戏内手势开关，以及可选的 Steam 主界面最高 60 Hz/60 FPS 开关。后者依赖新版 Gamescope，并使用会话用户的 X11 root properties。2026-10-24 的已安装验证对应旧版；本次构建与测试状态见 [同步记录](../../docs/freedom-sync-20261029.md)。
