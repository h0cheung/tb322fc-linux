# 按需 USB 文件传输

引用 Freedom 固定提交 `9788014a0293dc26745b000d02854ad88ef73e88` 的 gadget、存储选择及服务文件，保留 SHA256 校验；Arch 用户和 USB 角色行为由本地补丁适配。`umtp-responder-freedom` 则引用 uMTP 1.9.1 的固定提交，以及 Freedom 的5个原始补丁。

接上电脑后，在 Freedom Control 打开 MTP，或执行：

```sh
sudo systemctl start armada-mtp.service
sudo systemctl stop armada-mtp.service
```

服务默认关闭、不随开机启动。它按活动图形会话解析用户，向电脑共享其可见 Home 文件；若检测到唯一、已挂载且该用户可读写的 SD 卡，也共享该卡。隐藏文件不展示；uMTP会跟随目录软链接，目录环不受支持。

gadget 配置由 root 创建，传输进程降权为会话用户。只绑定内核已经注册的唯一 USB device controller；没有电脑连接或存在多个控制器时失败退出，不强制切换 Type-C 角色或操作 GPIO。停止时解绑 gadget、卸载 FunctionFS 并删除运行时配置，保留内核自身的端口选择。

已验证四代连接 Windows 后枚举 Home、中文文件名和双向复制，内容哈希一致；停止后挂载、gadget和进程均清理。SD 卡共享尚未实机验证。
