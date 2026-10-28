hone 项目最终候选（C 集成协调提交）

仓库（共同主工作树）：E:\项目_手动重构\build\final-hone-dh1b_5mf\project\workspace\cooperation\8e577bfc8472\main
统一 HEAD：59d81758355bf1e5035d798eae2c6f720e5e462c
成员 worktree：workers\05cbb8c85608d9d9（A）、workers\6fe0f5dd8699d140（B/D）、workers\a1cd40ea5264c9e7（C）、workers\2f4505d1e7751870（E）
候选 ID：本次 datanet_team_finish action=propose 返回的 candidate_id（最终候选，待全员 approve）

交付内容：
- 可导入包 hone：hone/__init__.py、hone/hone.py、hone/utils/{__init__,csv_utils,json_utils,test_utils}.py；hone.Hone is hone.hone.Hone。
- CLI：hone/__main__.py，支持 `python -m hone` 与安装后 `hone` 命令，main(argv=None)->int。
- 测试：tests/ 69 个用例（schema/convert/csv_utils/special_csv/cli/packaging/examples），另有独立验收 scripts/verify_acceptance.py。
- 文档：README.md（安装 pip install .、CLI 文件输出、CLI stdout/stdin、Python API get_schema/convert、测试命令、行为与限制）、LICENSE、pyproject.toml（setuptools、[project.scripts] hone="hone.__main__:main"、packages.find include=["hone*"]）。
- 可安装构建产物：dist/hone-0.1.0-py3-none-any.whl（已 git 跟踪，12197 bytes）。
- pristine 样例：INPUTS.md/docs/data_file/examples 零改动。

完整测试命令与输出摘要（在 main 59d8175 的 worktree 执行）：
1) python -m unittest discover -s tests -t . -v → Ran 69 tests in 7.485s, OK
2) python scripts/verify_acceptance.py → AC1–AC15 全部 PASS；RESULT: 15 passed, 0 failed, 0 skipped
3) python examples/demo.py → 成功（AC9/AC15）
4) python -m pip wheel . --no-build-isolation -w dist → 成功生成 hone-0.1.0-py3-none-any.whl
5) 新建 venv 安装该 wheel 后 import hone / hone --help / python -m hone --help / 端到端转换均成功（AC14）
6) git diff --exit-code HEAD -- docs data_file examples → 退出 0；git status --short 为空

关键约束落实：csv.reader 默认方言 + newline=''/utf-8，无二次反转义；自动嵌套每层“最左合法切分”（head/tail 非空、head 不在本层剩余列名集合、至少 2 个同前缀、多候选取 find(d) 最小、等 idx 按 delimiters 顺序、全部 groups 递归）；example_b 为 a、a_b 叶子 + b.c.{d,e}、b.d.{e,f}，第二行 b.d.f=="12"；CSVUtils 懒解析缓存、stdin 只读一次；JSON indent=2/sort_keys=True/ensure_ascii=False + 末尾换行；CLI -d/-s 参数错误退出 2，运行期错误 stderr 单行 `hone: error: ...` 退出 1，无 traceback。

全员验收情况：A（core/schema）、B（utils/CSV）、C（CLI/打包/集成）、D（tests/docs）、E（独立验收）认领均已 complete 并整合；E 已在 59d8175 独立复跑 AC1–AC15 全 15 PASS；B/D 亦报告 15/15 PASS。请 A、B/D、E 阅读本候选并真实复跑 AC1–AC15 后 approve。