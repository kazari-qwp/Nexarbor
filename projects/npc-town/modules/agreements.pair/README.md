# 双方在场同意（agreements.pair）

通用的双人同意模块，装在协议办理地点。只负责登记双方同意并应用约定字段，不处理时间、怀孕、生产或模板创建。

- `inspect({})` 返回规则及请求者参与的协议。
- `agree({partner, rule, key})` 为真实请求者登记同意。双方必须是不同的 Agent，且实际位于同一协议地点；配置 address 时必须是该地点。
- 两人可以先后登记，无需同一 tick。同意记录绑定双方 place.info 的 visit 版本；任何一人离场再回来，先前未完成的同意失效，必须重新登记。
- 双方在同一次连续会面中都同意后，协议从 open 变为 completed，写入规则的 set_values；forbid_existing_pair 配合 pair_field 可建立双方关系引用。

rules 支持 cost、require_values、eligible_field、equal_fields、pair_field、require_pair、forbid_existing_pair 和 set_values。require_values 是严格等值要求，不是数值下限。具体字段以 module.json 为准。

参与者需装配 records.store 和 place.info；它们是跨节点协作者，requires 不会将其强制挂到办理地点。访问频道按实际拓扑授予，例如小镇的 location 关系。模块不再依赖 clock.counter，也没有 fulfill、delay_ticks、delivery_address 或模板操作。

登记时短锁办理地点与两位参与者，锁内重新检查在场、资格与行动点；失败整体回滚。key 与真实请求者联合去重，重试不重复扣费，相同 key 不能换对象或规则。

小镇中婚姻登记直接装在民政局；居民楼把它与 family.household 放在同一地点，通过本地调用组合。医院的 family.birth 独立处理待产者，不再要求双方同意。
