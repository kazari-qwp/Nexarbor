# 新工作区沙箱 ACL 初始化

首轮 0.3.11 重跑已完成两轮讨论，但执行组全部在终端启动前遇到 `SetNamedSecurityInfoW failed (Win32 5): grantWrite(workspace)`。观察者取消付费会话并关闭该独立测试客户端，保留 `build/hone-native-20261014-r1/framework-stop.json` 和原生轨迹。该轮不计项目通过。

与昨日目录比较：旧目录有当前用户的显式 FullControl，新目录从 E 盘继承修改权限。原生 Harness 同时写入 DACL 与低完整性标签，当前目录管理权限不足。

修复在 `adapters/harness/framework/windows-workspace.js`，基础 Python 与业务组件不改。挂载网络时仅给当前用户拥有的工作区增加当前用户的 ChangePermissions 和 TakeOwnership（WRITE_DAC / WRITE_OWNER），沿子目录继承。保留已有 ACL、所有者和沙箱模式；不向其他用户授予数据权限。非当前用户所有的目录不修改。

真实 Harness AclSandbox 测试复现原始 Win32 5；初始化后同一目录沙箱启动成功，内部文件写入成功，外部目录写入仍失败。重复初始化也成功。证据 `build/test-data/owner-acl-76ghVN/result.json`。调用系统 .NET ACL 接口，避免继承的 PowerShell 模块路径影响系统命令自动加载。

第二轮使用新 home、会话、网络和空工作区重新运行同一任务。首轮 Agent、记忆和代码不复用。版本 0.3.12。
