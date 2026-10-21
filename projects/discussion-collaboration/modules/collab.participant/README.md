# 执行组成员入口

装在执行组节点，与 Git 整合器本地协作。成员沿 `collaboration` 调用：

- `read`：读取提交、候选与成员状态，并返回调用者自己的 `self.id`、`self.branch` 和 `self.is_member`。
- `submit`：登记本人的真实 Git commit，整合器验证提交及分支。
- `approve` / `veto`：对当前候选认可或否决；省略候选编号时读取当前候选。

成员身份取实际 `ctx.requester_id`，由入口自动填入，成员无需连接根节点。`integrator_module` 配置同节点整合器的实际模块 ID。

Git commit 由成员先在自己的分支创建；这里登记成果和意见，候选合并、冲突及全员通过判断由整合器负责。
