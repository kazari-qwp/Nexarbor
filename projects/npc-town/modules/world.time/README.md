# 小镇时间更新器

world.time 只装在 text_file，接收 signal_channels（默认 tick），每份新信号更新原始总 tick，并按 labels 与 text_template 更新本节点正文。read 通过 channels（默认 time）返回 tick、天数和时段。

它不做存档，也不把时间暗中塞进角色提示。组装器沿 tail 读取正文，居民楼和医院沿 time 查询原始 tick。小镇专用的日历显示规则留在本模块。
