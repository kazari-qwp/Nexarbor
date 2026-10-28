# hone 0.1.0 发布说明

- 产物：`hone-0.1.0-py3-none-any.whl`（SHA256 `9A74FD4C6C9C498E3DF64C9C4813B42398BE2009F5DFF5E2C9D6AD26C1470D83`）
- 源码归档：`hone-0.1.0-source.zip`（由最终提交 `git archive` 生成，SHA256 `AED54AD6144ACF58A44EB9F3D2AAD32A171F3F1CBEB7BCB311FC905B475020EB`）
- 组内 Git 仓库：`workspace/cooperation/8e577bfc8472/main`
- 最终提交：`59d81758355bf1e5035d798eae2c6f720e5e462c`
- 最终候选：`7aa1b917-3373-4cbe-b708-bf0eaf8dfd50`（4 名执行成员全部 approve）
- 验收：`python -m unittest discover -s tests -t .` → 69 tests OK；`python scripts/verify_acceptance.py` → AC1–AC15 15 passed / 0 failed / 0 skipped；样例与文档零改动，工作树干净。

## 安装

```bash
python -m pip install hone-0.1.0-py3-none-any.whl
```

## 使用

```bash
hone examples/example_a.csv out.json
hone examples/example_b.csv -
hone - - < examples/example_c.csv
python -m hone examples/example_c.csv -
```

```python
import hone
Hone = hone.Hone()
schema = Hone.get_schema('data_file/small_cats_dataset/dataset.csv')
result = Hone.convert('data_file/small_cats_dataset/dataset.csv', schema=schema)
```

README、完整源码、测试与验收脚本见组内 Git 仓库。
