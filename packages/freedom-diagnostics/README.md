# Freedom 诊断工具

引用 Freedom 固定提交 `9788014a0293dc26745b000d02854ad88ef73e88` 的原始文件并校验 SHA256，本地只维护采集边界和 Arch 会话适配补丁。

- 默认只在休眠恢复后追加唤醒 IRQ 台账：`/var/lib/armada/wake-ledger.log`，超过500行保留最新250行。
- `armada-sleep-debug` 接通现有 Freedom Control 的休眠诊断功能。默认不开启详细采样或 trace；用户打开 Control 的诊断开关后，由现有 hook 采集并导出到会话用户的 `Documents/sleep-logs`。
- devcoredump 自动保存到 root 私有目录 `/var/lib/armada/devcoredump`。单份最多128MiB，最多8份，保留总量最多512MiB；超限内容保存为 `.truncated.devcore`，不是完整转储。目录锁串行采集，临时文件有独立的单份上限。
- tmpfiles 分别清理7天前的 devcoredump 和14天前的持久诊断记录。上游报告器另限制32轮记录和10轮已导出的运行时记录。

本包只观察系统，不替换休眠入口、修改电源策略或主动挂起设备。诊断中的“无数据”不等于数值为零，也不保证故障一定产生内核转储。
