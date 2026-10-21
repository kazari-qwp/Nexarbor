# 医院生产

family.birth 只要求待产者本人到医院。沿 time_channels 查询唯一 world.time，以当前 tick 减 pregnancy.start_tick，达到 duration（默认 10）即可生产，不重新要求双方同意。

模板按住所选择，先短事务保存稳定待办，再调用 templates:instantiate 创建独立儿童及其上下文装配和工具来源；当前样板的组装器在儿童本节点，工具收集器在亚节点；重试复用同一模板 key。随后清除怀孕词条和资料连接，添加家长资料与儿童引用。父母须可达但不要求陪同到医院。新生儿的能力由完整模板装配，不靠查询全图补齐。
