# 模块局部视图更新包 2026-10-28

更新包：build/release-module-view/Nexarbor-0.9.2-win-x64.zip，313,369,876 bytes（约298.85 MiB）。

SHA-256：ae67ce88261f2a347cb8ebda94ff67e28b3dc832b9c3b84d1b92fc1c834f65a1

源码提交：5a950d82537b728995fc3f80bac220ba69520c7b。旧build/release保持原样；其解压目录正在被客户端使用，更新包单独交付。完整解压新包后运行Nexarbor.exe。

本版包含模块左键局部视图、工作区恢复及7个无用通信节点清理，沿用已有亚节点筛选。当前小镇45节点、156条连接、7个Agent；最终仍为tick30，消息历史保留。core没有本次修改，包内包含用户原有DataNode改动，SHA记入release.json且未暂存。

ZIP的11059个条目通过SHA/CRC校验，重新解压后的独立Python导入通过。实际解压EXE使用包内Python、移除开发环境PATH后，首页/Harness设置、六份演示冷打开及最终历史双击全部通过，节点数2/18/4/7/45/45；最终小镇还实测了模块左键局部视图并返回全局。pageerror/API错误为空，模型调用0。扫描10858个文件，实际凭据匹配0。

Python全量526项通过，前端全量137项通过；详细变更见MODULE_VIEW_20261028.md。完整机器证据见evidence/2026-10-28-release-module-view.json及交付目录VERIFICATION.json。真实包截图见screenshots/release-module-local-20261028.png。
