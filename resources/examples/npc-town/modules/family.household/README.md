# 居民楼家庭计划

family.household 与 agreements.pair 同装在居民楼，直接本地调用其 family_plan 规则，要求双方实际在场、共同住所正确；两人连续在场先后同意即可，无需同 tick。

同意完成后沿 time_channels 查询唯一 world.time，为具备 can_gestate 的参与者写 pregnancy.start_tick 等记录，并把 pregnancy_channels 找到的文本接到其上下文。相同协议重试不重复写入。不维护孕期自增计数，也不处理生产。
