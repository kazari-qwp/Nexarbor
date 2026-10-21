# hone 实现任务资料

- `docs/PRD.md`：需求与验收标准。
- `docs/architecture_design.md`、`docs/UML_class.md`、`docs/UML_sequence.md`：软件结构与接口说明。
- `data_file/`、`examples/*.csv`：可用于自行测试的输入样本。
- `data_file/small_cats_dataset/nested_schema.json`：可用于测试指定结构的输入 schema。
- `examples/demo.py`：包调用的示例接口。

实现可导入的 `hone` 包，并提供 `python -m hone` 命令行入口。`Hone` 位于 `hone.hone`，按资料实现转换与 schema 接口；核心功能使用 Python 标准库。命令行参数按 PRD，README 写明文件输出及标准输出的可运行示例。样例文件保持原样，实现与自测放在自己的工作目录。
