# 可选超分与插帧

Decky 面板“超分与插帧”按游戏管理 OptiScaler 和 Kettle Framegen。默认均关闭，插件不改电源策略、引擎设置或其他游戏的配置。Kettle 的后端与界面片段使用固定 URL、SHA256 和本地兼容补丁引用，来源见 `upstream-sources.json`。

OptiScaler 提供 SGSR2、Arm ASR、FSR2.2；在游戏已有的 DLSS / FSR2+ / XeSS 选项中启用对应接口。它会在选择的 exe 目录放置代理 DLL 和配置；关闭时恢复原文件、原 DLL 覆盖值，并保留用户期间手动更改的覆盖设置。AMD FSR3 和闭源 DLL 不随包提供。

Kettle 插帧支持2倍、3倍或自动倍率。启动参数会在已有包装器之后插入 `kettle-fg`，仅对该游戏停用 LSFG。保留交换链图像数、WSI 绕过和运动估计分辨率可单独设置。修改交换链或 WSI 设置后需重启游戏；倍率等配置由库在运行中重读。显示刷新率和 Steam 帧率上限仍在 Steam 性能菜单设置；固定2倍时建议基础帧率为显示帧率的一半。

本面板使用标准 Decky API 和无 root 权限的 Python 后端；Loader 更换不属于本包安装动作。系统副本由 `render-tools-sync` 在 `decky-loader@` 启动前同步，用户设置与游戏配置保存在用户目录。

面板用“超分／插帧”两个页签直接切换，并在 QAM 关闭、重建后保留当前页签。页签组件按固定 Kettle 提交引用。关闭超分时显示的 Game folder 和 Load as 分别选择实际 exe 目录与代理 DLL 名称；启用前确定，修改时先关闭以恢复原文件。

Game folder 和 Load as 在选择时立即按游戏保存；关闭、重新打开 QAM 或重启 Loader 后仍保持。保存选择时不复制 DLL，也不修改启动参数，启用超分后才安装。
