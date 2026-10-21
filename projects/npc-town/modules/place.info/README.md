# 位置资料

`place.info` 可装在地点和 Agent 上，提供本地说明、visitors、location 和 visit。

- read 接受 movement、info、road 或 location。它只查询本节点资料，不扫描全图。
- arrive / leave 接受 movement、road 或 location，只能修改真实请求者自己的访客记录。
- set_location 使用同样的修改频道；只能由新地点为实际发起移动的 Agent 更新位置和尾部说明。位置变化时 visit 加一，供连续在场判定。

visitors_from_edges 默认 false，使用配置/状态中的访客表。设为 true 时，从地点自己的出边派生访客：关系为 location，且频道含 location、movement、road 中任一个；结果去重排序，不合并旧访客记录。Agent 上禁止该模式。

小镇位置边统一用 location，道路用 road。info 仅放宽读取，不能单独授权 arrive、leave 或 set_location；实际操作仍受模块授权、真实请求者身份与路径约束。移动模块在短事务中更新双方资料及连接，失败由核心回滚。
