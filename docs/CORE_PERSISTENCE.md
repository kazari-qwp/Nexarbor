# 核心增量日志、全量快照与统一恢复点

核心持久化协议不依赖Harness，不作为网络节点或应用扩展。当前是核心阶段：执行器凭据可存储、标记、导出和交接；Harness原生日志位置的真实采集与按位置分叉仍需后续适配层实现，不能据此宣称已经完成Harness上下文一键回档。

## 状态写入

checkpoints.sqlite3使用SQLite WAL和synchronous=FULL。首次提交保存完整状态；后续保存确定的JSON状态差异（set/remove/append/truncate），按提交序号和前后SHA-256校验链连接。恢复只重放状态值，不重新执行工具、模型、交易或其他副作用。未变化的状态不新增提交；操作完成仍清除对应pending记录。

默认每100个提交生成全量快照，可通过Backend(directory,snapshot_interval=...)设置；显式save(full=True)或创建full恢复点也生成全量。增量恢复选择不晚于目标提交的最近快照，再重放到目标；已保留的恢复点与日志不自动清除。当前没有做历史保留策略，避免错误删除恢复点依赖。

不再每次提交写临时全量network JSON文件。当前仍在内存中汇总状态并比较差异，优化的是持久化写入及历史大小，不声称已实现各业务字段的自动写跟踪。核心登记文件仍按已有资源清单保存，外部资料与原生日志不自动打包。

操作前写pending日志，成功提交状态与清除pending在同一SQLite事务；中断或异常留下的uncertain操作不自动重跑。恢复点遇到不确定操作拒绝发布，宿主核对后可带理由reconcile。

旧的仅全量检查点数据库明确拒绝，不在此轮迁移，测试使用新目录。网络JSON仍沿用当前v5；这里升级的是数据库持久化格式v2。

## 统一恢复点

```python
info=backend.dispatch('persistence_info',{})
point=backend.dispatch('persistence_mark',{
  'kind':'incremental',  # 或full
  'expected_commit':info['commit_id'],
  'contexts':{
    'root':{'adapter':'example','session':'session-id',
            'position':{'seq':123,'generation':'log-generation'}}
  }
})
```

contexts是按Agent节点ID索引的不透明JSON对象，核心不解析执行器日志格式。必须覆盖当前所有已绑定会话，纯核心无会话可传空对象。适配层应先在一致边界刷盘并提供真实位置，再用expected_commit发布；网络版本变化则拒绝，避免错配。恢复点编号独立于状态提交编号，因此网络没变但会话推进时仍可建立新点。恢复点与完整快照关联在同一数据库。

```python
backend.dispatch('persistence_points',{})
bundle=backend.dispatch('persistence_export',{'point_id':point['id']})
result=backend.dispatch('persistence_restore',{
  'point_id':point['id'],'directory':'E:/new-empty-recovery-directory'
})
```

恢复包包含核心完整状态、统一标记和校验和（覆盖状态及会话标记），不用原核心数据库即可恢复。会话标记仍依赖对应执行器原日志，导出包不是原生日志的副本。仅允许新/空目录，保留原分支，不覆盖运行中的网络。

有上下文的恢复先标记executor_restore pending，Application拒绝挂载Agent，防止自动恢复最新会话。适配层真正恢复/分叉每个保存位置后，回报新会话ID：

```python
branch.dispatch('persistence_executor_restored',{
  'sessions':{'root':'restored-or-forked-session-id'}
})
```

必须覆盖全部待恢复节点且会话ID唯一；相同回执可重试。核心先持久化新绑定，再确认就绪。该回执是可信适配层契约，核心不能自行验证外部执行器是否真的完成恢复。无会话的纯核心恢复可直接使用。

## 最小验证

36项通过：新增日志/恢复7项、原核心信号20项、四口输入4项、装配器5项。覆盖嵌套差异、数组增删、负零变化、无变化不增量、周期/显式全量、历史恢复、崩溃未提交、校验损坏、乐观提交版本、不透明会话位置、记忆恢复、原分支保留、上下文恢复门禁、回执幂等、旧格式拒绝和文件锁释放。未调用模型API。Harness原生真实位置的标记/回放测试尚未执行。

额外回归：全新工作区的真实Harness服务+Mock模型单NPC回环通过，原生上下文、四口输入及正常回源仍工作。这不代表已实现原生日志位置回档。
