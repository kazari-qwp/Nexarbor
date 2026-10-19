# 地点与处境查询

只提供查看处境、查询地点、查询地图三个按需工具。依赖本地 records.store / place.info，外部读取通过模块的 movement / records / info 授权。地图由可达地点道路生成 PNG，不含私人记忆或人格。

publish 是显式准备操作，按 public_fields 发布公开人物资料。角色执行配置可以在上下文准备前调用它。它不写四路输入，不扫描提示词，不承担角色的活动调度。clock、map_title、map_layout 都是可见配置。
