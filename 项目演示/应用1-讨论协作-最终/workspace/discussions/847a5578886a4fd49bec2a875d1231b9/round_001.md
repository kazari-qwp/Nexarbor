## 第1轮 · admin-9faf6c13a8bb4bde889aec9593a327b1
# hone 实现计划（执行组任务说明 v1）

## 0. 前置约定（先冻结，再并行）
- 仓库根 = 执行组自建 git 仓库；用 `git.workspace` 初始化，根目录不代写实现。样例/文档从 `workspace/task/` **逐字节复制**（`data_file/`、`examples/`、`docs/`），不重排格式、不改内容。
- 语言/依赖：Python ≥3.8，核心仅标准库（csv/json/argparse/contextlib/ast/sys/io）。
- 代码风格：4 空格、UTF-8、`open(..., newline='', encoding='utf-8')`；禁止在 `hone/` 内读取 `workspace/task` 的绝对路径。
- 接口契约一旦冻结，只有 M1 可改签名，且需在群里广播。

## 1. 仓库与文件布局
```
hone/                          # git 根
├── hone/
│   ├── __init__.py            # from .hone import Hone; __all__=["Hone"]; __version__
│   ├── hone.py                # Hone 类（唯一实现核心）
│   ├── __main__.py            # argparse + main(); console_scripts 入口
│   └── utils/
│       ├── __init__.py
│       ├── csv_utils.py       # CSVUtils + 全局函数 parse_csv_file
│       ├── json_utils.py      # output_json / parse_json_file + 全局函数
│       └── test_utils.py      # 测试辅助：load_json_fixture / assert_json_equal / csv_text
├── tests/
│   ├── __init__.py
│   ├── test_csv_utils.py
│   ├── test_schema.py         # 自动 schema/嵌套算法
│   ├── test_convert.py        # 三组 data_file + examples + schema 指定
│   └── test_cli.py            # CLI 文件/stdio/-m hone/错误码
├── data_file/                 # 原样复制（3 个数据集，含 nested_dataset.json / nested_schema.json）
├── examples/                  # 原样复制（demo.py/demo.sh/README.md/example_a|b|c.csv）
├── docs/                      # 原样复制（参考资料）
├── README.md                  # 新写：安装、CLI 文件输出 + stdout 两个可运行示例、Python API、测试
├── LICENSE                    # MIT
└── pyproject.toml             # 打包最小集
```
pip 可导入/安装最小文件：`pyproject.toml` + `hone/__init__.py`（`pyproject` 用 setuptools：`[project] name="hone"`、`version`、`requires-python`、`readme`、`license`、`[project.scripts] hone="hone.__main__:main"`、`[tool.setuptools.packages.find] include=["hone*"]`）。`setup.py` 不写；额外提供 `setup.cfg` 可选，不必须。

## 2. 接口与算法（冻结签名）
```python
class Hone:
    DEFAULT_DELIMITERS = [",", "_", " "]
    def __init__(self, delimiters=None)                # None→DEFAULT；list[str] 保序；空值/非 str → ValueError
    def get_schema(self, csv_filepath) -> dict         # 嵌套 schema，叶子值=原始列名
    def convert(self, csv_filepath, schema=None) -> list[dict]
    def populate_structure_with_data(self, structure, column_names, data_rows) -> list[dict]
    def generate_full_structure(self, column_names) -> dict
    def get_nested_structure(self, parent_structure)
    def get_leaves(self, structure, path=None, result=None)
    def get_valid_splits(self, column_name) -> list[list[str]]
    def get_split_suffix(self, split, column_name) -> str
    def clean_split(self, split)
    def is_valid_prefix(self, prefix, base) -> bool
    def set_csv_filepath(self, csv_filepath)           # setter；convert/get_schema 内部调用
    @staticmethod
    def escape_quotes(s) -> str                        # '"'→'\\"'
class CSVUtils:
    def __init__(self, csv_filepath)
    def open_csv(self, mode="r", newline="") -> contextmanager  # filepath=="-" 时用 sys.stdin/sys.stdout
    def get_column_names(self) -> list[str]            # 首行
    def get_data_rows(self) -> list[list[str]]         # 其余行，跳过纯空行
```
- `convert(csv_filepath, schema=None)`：schema 为 None/缺省 → `get_schema` 自动生成；schema 为 str → `json.loads`；为 dict → 直接用。返回 `list[dict]`，每行一个 dict。
- 自动 schema / 嵌套算法（要点）：
  1. 记 `S = set(column_names)`；候选切分点 = 任一 delimiter 的任一出现位置，切成 `prefix/suffix` 两段。
  2. 合法性（三条同时满足）：`prefix` 非空且 `suffix` 非空；`suffix` 首字符为字母/数字（`clean_split`：拒绝 `(kg)`、`"`、空格开头等，故 `weight (kg)`、`age (years)` 保持扁平）；`prefix not in S` 且 **prefix 是至少 2 个列名的“分段边界前缀”**（避免把唯一前缀拆开，如 `some 'quoted"' field"`；也避免 `"test","ing"` 被逗号拆开）。
  3. 多 delimiter 冲突时取**最左合法切分**，对 suffix 递归再切（`b_c_d` → `b → c → d`）。
  4. 关键用例：`a_b` 的 prefix `a` 是叶子列（`a in S`）→ 不拆，保留 `a_b`；`adopted_since` 的 prefix `adopted` 是叶子 → 不拆；`birth day/month/year` 的 `birth` 非叶子且被 3 列共享 → 嵌套 `birth`；`b_c_*`/`b_d_*` → `b.{c,d}`。
  5. 生成结构：叶子路径写入 `{父: {子: 原始列名}}`；若切分导致与已有叶子键冲突，该列退化为扁平原名（确定性回退，不抛异常）。
- `populate_structure_with_data`：按 schema 递归；叶子值 v → `column_names.index(v)` 取该行值；行短于表头补 `""`，超长忽略；缺列不 KeyError。`get_leaves` 产出 `(path, source_name)` 供复用。
- CSV/引号：用 `csv.reader` 默认方言（`delimiter=","`、`quotechar='"'`、`doublequote=True`），配合 `newline=''`。`comma_test` 的期望键/值（`"test","ing"` / ` "beep"""`、`"1` / `"2`）属于 csv 模块宽松解析结果，**M1 先写探针脚本 `python -c` 打印 csv.reader 结果并与 `nested_dataset.json` 对照**，若不一致只允许调 `skipinitialspace/quotechar` 等 reader 参数，不允许手写解析器。
- JSON 输出：`json.dump(obj, indent=2, sort_keys=True)` + 结尾换行；`ensure_ascii=False`。

## 3. CLI（`hone/__main__.py`）
- `argparse.ArgumentParser(prog="hone")`：位置参数 `csv_filepath`、`json_filepath`；`-d/--delimiters`（`nargs="?"`，默认 `"[',', '_', ' ']"`，`ast.literal_eval` 优先、失败回退 `json.loads`，必须得 list[str]，否则 `parser.error`）；`-s/--schema`（`nargs="?"`，`json.loads`，必须是 dict）；帮助文本与 docs/README 的 `hone --help` 对齐。
- 流程：parse → `Hone(args.delimiters).convert(args.csv_filepath, args.schema)` → `output_json(struct, args.json_filepath)`。
- `-` 语义：csv 为 `-` 读 `sys.stdin`；json 为 `-` 写 `sys.stdout`（只写 JSON，不加日志）；否则写文件（`indent=2, sort_keys=True`）。
- 退出码：0 成功；2 argparse 用法错误（坏 `-d`/`-s`）；1 运行错误（文件不存在、schema 非法 JSON/非 dict、解码失败），`stderr` 输出 `hone: error: <msg>`，不打 traceback。
- `main()` 返回 int，`if __name__ == "__main__": sys.exit(main())`；`python -m hone` 与安装后的 `hone` 行为一致。

## 4. 验收用例（每项含负责人/路径/命令）
| # | 验收项 | 负责人 | 产出/命令 |
|---|---|---|---|
| A1 | 包可导入：`import hone; hone.Hone; from hone.hone import Hone` | M1 | `python -c "import hone; print(hone.Hone().DEFAULT_DELIMITERS)"` |
| A2 | `comma_test/dataset.csv` 自动转换与 `nested_dataset.json` **语义相等**（`json.load` 后 `==`，不做文本 diff） | M1 | `python -m unittest tests.test_convert -k comma` |
| A3 | `quotes_test` 转换与 `nested_dataset.json` 语义相等（引号/单双引号/逗号字段） | M1 | 同上 `-k quotes` |
| A4 | `small_cats_dataset` 自动转换与 `nested_dataset.json` 语义相等 | M1 | `-k small_cats` |
| A5 | 指定 `nested_schema.json` 转换，结果与 `nested_dataset.json` 相等 | M1 | `-k schema` |
| A6 | `example_b.csv` 自动嵌套 = `a`、`a_b` 扁平 + `b.c.{d,e}` + `b.d.{e,f}`（第二行 `b.d.f="12"`，见风险 R1） | M1 | `-k example_b` |
| A7 | `example_a/c.csv` 与 examples/README 期望一致 | M4 | `-k example` |
| A8 | CSVUtils 列名/数据行、空行跳过、`-` stdin | M2 | `python -m unittest tests.test_csv_utils` |
| A9 | CLI 文件输出：`python -m hone data_file/small_cats_dataset/dataset.csv /tmp/o.json && python -m json.tool /tmp/o.json`，且键序 sorted、indent=2 | M3 | 贴命令+`diff <(python -m json.tool /tmp/o.json) <(...)` |
| A10 | CLI stdout：`python -m hone examples/example_a.csv - | python -c "import json,sys;json.load(sys.stdin)"` | M3 | 同上 |
| A11 | stdin 输入：`cat examples/example_c.csv | python -m hone - -` 输出合法 JSON | M3 | 同上 |
| A12 | 错误处理：不存在文件 → 退出码 1 且 stderr 有提示；`-d "not a list"`/`-s "{bad}"` → 退出码 2 | M3 | `python -m hone /nope.csv -; echo $?` |
| A13 | 安装性：`python -m venv .venv && .venv/bin/pip install .`（无网则 `--no-build-isolation`），新进程 `import hone` + `hone --help` + `python -m hone` | M3 | 贴 `pip install / __version__` 输出 |
| A14 | 全量测试：`python -m unittest discover -s tests -v` 全绿 | M4 | 汇报用例数 |
| A15 | README 含文件输出与 stdout 两个真实可跑示例（命令+期望片段） | M4 | 人工+复制命令执行 |

## 5. 四人分工（路径不重叠，Git 可并行）
| 成员 | 角色 | 独占路径 | 自测命令（完成后贴群） |
|---|---|---|---|
| M1 | core/schema | `hone/hone.py`、`hone/__init__.py` | `python -c "from hone.hone import Hone; ..."`；`python -m unittest tests.test_schema -v`（消费 M4 夹具）；本地 `python examples/demo.py` |
| M2 | CSV/JSON utils | `hone/utils/**`（`__init__.py`、`csv_utils.py`、`json_utils.py`、`test_utils.py`） | `python -m unittest tests.test_csv_utils -v`；`python -c "from hone.utils.csv_utils import CSVUtils; ..."` |
| M3 | CLI/打包 | `hone/__main__.py`、`pyproject.toml`、`LICENSE` | `python -m hone --help`；A9–A13 命令；`pip install .` 冒烟 |
| M4 | 测试/文档/夹具 | `tests/**`、`README.md`、`data_file/**`、`examples/**` | `python -m unittest discover -s tests -v`；README 命令逐条复跑 |
- 协作顺序：M1 先 30 分钟内提交可导入骨架（`Hone.__init__` + 空 `convert` 抛 `NotImplementedError` 亦可），M2/M3/M4 按冻结契约并行；M4 的测试先按契约写（可先红后绿）。集成由 M3 在 `main` 上跑 A1–A15，M1 修算法、M2 修 IO、M4 修断言。**任何人不得改他人独占文件**；需要改契约先群里说、由 M1 落地。
- Git：每人一个分支 `feat/<role>`，提交信息 `feat(core): ...`；M3 负责合并与冲突裁决（只会在 `tests/`/`docs/` 边缘冲突）。

## 6. 风险点与对策
- R1 `examples/README.md` 中 example_b 第二行 `b.d.f` 写作 `"1"`，与 CSV 的 `12` 矛盾（明显笔误，且仓库无 example_b.json）。**以算法正确输出 `"12"` 为验收**，测试用显式期望结构，不读该 README 片段；不修改样例文件，在 README/测试注释说明。
- R2 期望 JSON 的键序/缩进与 `sort_keys=True` 不一致（quotes_test 非排序）。**一律 `json.load` 语义比较**，禁止文本 diff 作为验收。
- R3 `comma_test` 依赖 csv 模块宽松引号解析，手写解析器会失败。先探针后实现。
- R4 嵌套切分歧义（共享前缀/叶子冲突）易回归。用 example_b + `adopted_since` + `weight (kg)` + quotes 表头做参数化回归。
- R5 `-` 与 Windows 换行：`newline=''`、`sys.stdin` 不重复包装、输出加末尾换行。
- R6 pip 安装需构建后端/可能无网：优先 `--no-build-isolation`，`pyproject` 只依赖 setuptools；退化方案是 `pip install -e .` 也须通过。
- R7 空行/行列不齐导致 KeyError：补 `""` 或忽略超长，测试覆盖。
- R8 重复列名：保留首次出现、后者不覆盖（低风险，测试中不主推）。
- R9 职责越界改样例文件：M4 复制后 `git diff --stat` 校验 `data_file/`、`examples/` 零改动。

## 7. 交付定义（Definition of Done）
`pip install .` 成功；`import hone` + `python -m hone` 可用；A1–A15 全绿并附命令输出；`git status` 干净；样例文件字节未变；README 示例可直接跑通。

## 第1轮 · admin-2582a4ee77774edd882b92a04b5dde8f
# hone 实现计划（Leader 第1轮草案，供 Recorder 直接采纳/修订）

## 0. 结论先行（冻结的契约）
- 仓库根 = `workspace/task`（由执行组用 git.workspace 初始化，先提交 pristine 快照；`examples/`、`data_file/`、`docs/`、`INPUTS.md` 一字不改）。
- 唯一对外入口：`hone.Hone`（定义在 `hone/hone.py`，`hone/__init__.py` 只做 re-export）；CLI 入口 `python -m hone`。
- 只允许标准库：`csv, json, argparse, contextlib, ast, sys, io, os, copy, unittest, pathlib`（`ast` 仅用于解析 `-d` 的 Python 字面量列表）。
- 所有成员必须按第 2 节签名写代码，不得改签名、不得改默认值；集成冲突由 Recorder 按本节裁决。

## 1. 仓库与文件布局（含 pip 安装最小集合）
```
hone/__init__.py            # from .hone import Hone; __all__=["Hone"]; __version__="0.1.0"
hone/hone.py                # Hone 类（schema 生成 + populate + convert）
hone/__main__.py            # argparse CLI：main(argv=None)->int + __main__ 调用
hone/utils/__init__.py
hone/utils/csv_utils.py     # CSVUtils
hone/utils/json_utils.py    # output_json / parse_json_file / parse_csv_file
hone/utils/test_utils.py    # 测试辅助（JSON/CSV 比较）
tests/__init__.py
tests/test_hone_schema.py
tests/test_csv_utils.py
tests/test_cli.py
tests/test_integration_data_files.py
pyproject.toml
README.md                   # 覆盖为可运行说明（文件输出 + stdout 示例）
LICENSE                     # MIT
.gitignore                  # __pycache__/ *.egg-info/ dist/ build/ .venv/
```
pip 可安装最小集合：`pyproject.toml` + `hone/__init__.py` + `hone/hone.py` + `hone/utils/*`（`__main__.py` 供 `python -m hone`）。`pyproject.toml` 关键内容：
```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"
[project]
name = "hone"; version = "0.1.0"; requires-python = ">=3.8"
description = "Convert CSV to automatically nested JSON"
[tool.setuptools.packages.find]
include = ["hone*"]
```
（可选 `[project.scripts] hone = "hone.__main__:main"`，但验收只要求 `python -m hone`。）

## 2. 冻结接口（逐字照此实现）
```python
# hone/hone.py
class Hone:
    DEFAULT_DELIMITERS = [",", "_", " "]
    def __init__(self, delimiters=None): ...          # None -> DEFAULT_DELIMITERS 的拷贝
    def get_schema(self, csv_filepath) -> dict: ...
    def convert(self, csv_filepath, schema=None) -> list[dict]: ...
    def populate_structure_with_data(self, structure, column_names, data_rows) -> list[dict]: ...
    def generate_full_structure(self, column_names) -> dict: ...
    def get_nested_structure(self, parent_structure) -> dict: ...
    def get_leaves(self, structure, path=None, result=None) -> list[tuple[list[str], str]]: ...
    def get_valid_splits(self, column_name) -> list[list[str]]: ...
    def get_split_suffix(self, split, column_name) -> str: ...
    def clean_split(self, split) -> list[str]: ...
    def is_valid_prefix(self, prefix, base) -> bool: ...
    def set_csv_filepath(self, csv_filepath) -> None: ...
    def escape_quotes(self, string) -> str: ...        # 纯辅助，禁止在 json.dump 前调用（避免双重转义）
```
```python
# hone/utils/csv_utils.py
class CSVUtils:
    def __init__(self, csv_filepath): ...
    def get_column_names(self) -> list[str]: ...        # 首条记录
    def get_data_rows(self) -> list[list[str]]: ...      # 首条之后的所有记录
    def open_csv(self, mode="r", newline=""): ...        # contextlib.ExitStack；filepath=="-" 时用 sys.stdin
    # 内部：_read_all() 只解析一次并缓存（stdin 不可回绕，必须靠缓存）
```
```python
# hone/utils/json_utils.py
def output_json(json_struct, json_filepath): ...   # json.dump(indent=2, sort_keys=True)，末尾换行；"-" -> sys.stdout
def parse_json_file(json_filepath): ...            # "-" -> json.load(sys.stdin)
def parse_csv_file(csv_filepath): ...              # 返回全部记录（含首行），供 fixture 测试用
```
`hone/utils/test_utils.py`：`compare_structures(a,b)`、`assert_json_equal(testcase, actual, expected)`、`read_fixture_rows(dirpath)` 等，只被 tests 使用。

### 2.1 自动 schema 算法（核心，必须复现全部样例）
语义：schema 是"结构骨架"，**叶子值 = 原始列名**，键 = 拆分后的末段名。故 `nested_schema.json` 与自动生成 schema 同构，`convert` 统一处理。
递归建树 `_build(items)`，`items=[(original_name, remaining_suffix)]`：
1. `names = {suffix for _, suffix in items}`；收集候选切分：对每个 `suffix`、按 `self.delimiters` 顺序，若 `d in suffix`，取 `prefix=suffix.split(d,1)[0]`、`rest=suffix.split(d,1)[1]`（非空）。
2. 候选 `prefix` 合法 iff：(a) `prefix not in names`（否则键既是叶子又是对象，冲突：`a` 与 `a_b`、`adopted` 与 `adopted_since`）；(b) `prefix` 被"共享"：≥2 个 `items` 的 suffix 满足 `startswith(prefix + d)`（否则 `age (years)`/`weight (kg)`/`some 'quoted"' field"` 不应被拆）。
3. 选择**最短**合法 prefix（等长按 delimiters 顺序、再字典序）→ 只对该 prefix 建一个子对象，其余保持叶子：`schema[prefix] = _build([(orig, rest_of(prefix+d)) ...])`；不在该组内的 `(orig, suffix)` 直接 `schema[suffix] = orig`。
4. 返回 dict。示例校验：
   - example_b：`a`+`a_b`：`a` 是同名列 → `a_b` 保持叶子；`b_*` 选最短共享 `b` → 递归得 `b.c.{d,e}` 与 `b.d.{e,f}`。
   - small_cats：`birth` 组嵌套；`adopted_since` 的前缀 `adopted` 是同级列名 → 不拆；`age (years)` 前缀不共享 → 不拆。
   - comma_test：键含 `,` 但前缀不共享 → 保持原键。
5. `get_nested_structure(parent_structure)` 供兼容：把 schema 中所有 dict 分支规整为 `{key:{...}}` 形态（不得改变叶子）。
6. `populate_structure_with_data(schema, column_names, data_rows)`：
   ```
   index = {name: i for i, name in enumerate(column_names)}
   leaves = self.get_leaves(schema)         # [(path_list, source_column_name)]
   for row in data_rows:
       obj = {}
       for path, col in leaves:
           if col not in index: raise ValueError(f"schema column not found: {col}")
           value = row[index[col]] if index[col] < len(row) else ""
           node = obj
           for k in path[:-1]: node = node.setdefault(k, {})
           node[path[-1]] = value
       out.append(obj)
   ```
   （空值保留 `""`，不做类型推断；行短补 `""`，行长忽略多余列。）
7. `convert(csv_filepath, schema=None)`：`self.set_csv_filepath`；**只构造一次 CSVUtils**并先取 `column_names`、`data_rows`，`schema is None` 时 `schema = self.generate_full_structure(column_names)`，再 populate。`get_schema` 独立实现（同样 `generate_full_structure(get_column_names())`）。这样 stdin 也只读一遍。
8. 读取一律 `open(path, "r", encoding="utf-8", newline="")` + `csv.reader` 默认方言（**不要**自己处理引号）；引号/逗号/空值全部交给 csv 模块，`escape_quotes` 不参与转换链路。

## 3. CLI（`hone/__main__.py`）
```
usage: hone [-h] [-d [DELIMITERS]] [-s [SCHEMA]] csv_filepath json_filepath
```
- 位置参数：`csv_filepath`、`json_filepath`，`"-"` 分别表示 stdin/stdout。
- `-d/--delimiters`：`nargs="?"`，默认 `None`；值为 Python 兼容字符串列表，用 `ast.literal_eval` 解析（失败则尝试 `json.loads`，仍失败 → 退出码 2 并给 help 提示）；必须是 `list[str]`，否则 argparse error。
- `-s/--schema`：`nargs="?"`，默认 `None`；`json.loads` 解析，非法 JSON → stderr 报错，退出码 2。
- 流程：`args = parser.parse_args()` → `hone = Hone(args.delimiters)` → `result = hone.convert(args.csv_filepath, schema)` → `output_json(result, args.json_filepath)`。
- 输出：`json.dump(..., indent=2, sort_keys=True, ensure_ascii=False)` + 末尾 `"\n"`（stdout 与文件一致）。
- 退出码：0 成功；2 参数/JSON/字面量错误（argparse）；1 运行期错误（文件不存在、解码失败、schema 列名缺失等），错误信息写 stderr（`FileNotFoundError`/`ValueError` 捕获后打印，`main` 返回 1；`__main__` 中 `sys.exit(main())`）。
- README 必须给出两条可直接运行的命令：`python -m hone examples/example_a.csv out.json` 与 `python -m hone - - < examples/example_a.csv`。

## 4. 验收用例（每条：命令 + 预期 + 负责人 + 产出路径）
| # | 用例 | 命令/断言 | 负责 | 文件 |
|---|---|---|---|---|
| 1 | 三组 data_file 转换与 nested_dataset.json 一致 | 遍历 `data_file/{comma_test,quotes_test,small_cats_dataset}/dataset.csv`：`json.loads(json.dumps(Hone().convert(p))) == json.load(open(dir/'nested_dataset.json'))`（**比较解析后的对象，不比文本**，因 fixture 缩进/键序不同） | M4 | `tests/test_integration_data_files.py` |
| 2 | 指定 schema 转换 | `Hone().convert('data_file/small_cats_dataset/dataset.csv', schema=json.load(open('.../nested_schema.json')))` 等于 `nested_dataset.json` | M1 | `tests/test_hone_schema.py` |
| 3 | example_b 自动嵌套 | schema `b->{c:{d,e}, d:{e,f}}`，`a`、`a_b` 为叶子；example_a/example_c 与 `examples/README.md` 中 JSON 一致 | M1 | 同上 |
| 4 | 引号/逗号/空值 | `csv_utils` 解析 comma_test、quotes_test 的列名与数据行逐字段断言；`csv.reader` 结果不做后处理 | M2 | `tests/test_csv_utils.py` |
| 5 | CLI 文件输出与 stdout | subprocess 跑 `python -m hone examples/example_b.csv -` → 解析 stdout == 期望；写临时文件后解析 == 期望；`indent=2`/`sort_keys=True` 文本检查 | M3 | `tests/test_cli.py` |
| 6 | `python -m hone` / `--help` | `--help` 含两个位置参数与 `-d/-s`；`python -m hone` 从仓库根可运行 | M3 | 同上 |
| 7 | pip 安装可导入 | 临时 venv：`pip install . --no-build-isolation`（无网环境回退）→ `python -c "import hone; hone.Hone().get_schema('examples/example_a.csv')"`；`pip wheel . --no-build-isolation` 产物可装 | M3 | `tests/test_cli.py` 内 skip 或 README 验证脚本 |
| 8 | 样例零改动 | `git status --porcelain examples data_file docs` 为空 | M4 | 验收清单 |

全员统一自测命令（写进 README「Running tests」）：
```bash
python -m unittest discover -s tests -t . -v
python -m hone examples/example_b.csv -
python examples/demo.py
```

## 5. 四人分工（等权、路径不重叠，git 整合友好）
- **M1 core/schema**：`hone/__init__.py`、`hone/hone.py`、`tests/test_hone_schema.py`。负责第 2 节全部 Hone 语义与 schema 算法；自测：`python -m hone examples/example_b.csv -` 与用例 2/3。
- **M2 CSV/IO utils**：`hone/utils/__init__.py`、`hone/utils/csv_utils.py`、`hone/utils/json_utils.py`、`tests/test_csv_utils.py`。负责 csv 缓存单次解析、`-` 读写、`output_json` 的 indent/sort；自测：用例 4 + `python -c "from hone.utils.csv_utils import CSVUtils; ..."`。
- **M3 CLI/打包**：`hone/__main__.py`、`pyproject.toml`、`LICENSE`、`.gitignore`、`tests/test_cli.py`。负责 argparse、退出码、安装验证；自测：用例 5/6/7。
- **M4 测试/文档**：`tests/__init__.py`、`tests/test_integration_data_files.py`、`hone/utils/test_utils.py`、`README.md`。负责 fixture 对照、`python -m unittest` 全绿、文档与零改动核对；自测：用例 1/8。
整合协议：先 `git.workspace` 初始化并提交 pristine；各自只在本人路径提交（小步 commit，消息 `mN: ...`）；合并顺序 M2→M1→M3→M4（utils 先落地，core 依赖其签名）；冲突只能改自己文件，签名争议按第 2 节裁决；全员合并后跑统一自测命令，全绿才算完成。

## 6. 风险点与对策
1. **JSON 文本 vs 对象**：fixture 的缩进/键序与 CLI 输出不同 → 一律解析后比较，禁止 diff 文本。
2. **comma_test 的键依赖 Python csv 默认方言**（`"test","ing"`、` "beep"""`）：禁止自行 strip/反转义/改 quotechar；先写最小实验确认，再固化期望。
3. **前缀冲突**：`a`/`a_b`、`adopted`/`adopted_since` 若不判"prefix ∈ 同级列名"会生成非法结构 → 必须有该规则 + 单测。
4. **过度嵌套**：`age (years)`/`weight (kg)` 若不判"prefix 被 ≥2 列共享"会被错误拆开 → 单测锁定。
5. **stdin 不可回绕**：`convert` 中 schema 生成与取数若各开一次文件，`-` 会读到空 → 必须共用同一 CSVUtils 缓存（M2/M1 接口已约定）。
6. **-d 解析**：shell 引号易错 → 只接受单个字符串参数 + `ast.literal_eval`，README 写 `-d "[',', '_', ' ']"` 示例；错误退出码 2。
7. **pip 安装离线**：构建隔离需联网拉 setuptools → 文档给 `--no-build-isolation` 回退，并保证源码目录直接 `import hone` 可用。
8. **换行/编码**：`newline=""` + UTF-8，避免 CRLF 与引号字段被破坏。
9. **`escape_quotes` 误用**：一旦在写 JSON 前调用会双重转义 → 明确不进入转换链路，仅保留 UML 兼容方法。
10. **工期**：总改动约 400–600 行，建议 M2 先交付 utils 30 分钟，M1 并行写 schema，M3 用契约桩并行，M4 先写 fixture 测试再补文档。

（Recorder 可直接以本正文为输出板骨架；第 2 轮我会补：各成员接口签字确认、M2 的 csv caching 具体实现、以及 comma_test 键的实测结论。）

## 第1轮 · admin-c21fe857fa7e43bbabbb0ae6906387f1
# hone 实现计划（可直接作为执行组任务说明）

> 目标：交付可 `pip install .` 的 `hone` 包、`from hone.hone import Hone` 接口、`python -m hone` CLI；核心仅标准库；`data_file/`、`examples/` 样例保持原样；测试全绿。

## 0. 仓库初始化与协作规则
- 由执行组用 `git.workspace` 模块 `git init` 建仓（根不代写实现），先提交现有 docs/data_file/examples 作为基线。
- 分支：`feat/core`、`feat/utils`、`feat/cli`、`feat/tests`，各自只改自己名下文件；集成前 `git pull --rebase`，由 1 名成员做合并与冲突处理（建议 CLI 负责人兼任集成协调）。
- `.gitignore`：`__pycache__/`、`*.py[cod]`、`build/`、`dist/`、`*.egg-info/`、`.venv/`。
- 禁止修改 `data_file/**`、`examples/*.csv|*.json`；自测产物写到 `tmp/` 或测试临时目录。

## 1. 文件布局与负责人（尽量不重叠）

| 文件/目录 | 内容 | 负责人 |
|---|---|---|
| `hone/hone.py` | `Hone` 类、schema 算法、convert/populate | M1 core/schema |
| `hone/utils/__init__.py`、`csv_utils.py`、`json_utils.py`、`test_utils.py` | CSV/JSON 工具（含 `-` 标准流） | M2 utils |
| `hone/__init__.py`、`hone/__main__.py`、`pyproject.toml`、`README.md`、`LICENSE` | 包导出、CLI、打包、文档 | M3 cli/packaging |
| `tests/__init__.py`、`tests/test_*.py` | 单元+集成+CLI+打包验收测试 | M4 tests |
| 集成/合并 | 分支合并、最终 `git tag`、验收跑全量 | M3（协调）+ 全员 |

`hone/__init__.py` 只做 `from .hone import Hone`（+ `__all__`），不写业务逻辑，避免与 M1 冲突；M3 依赖 M1 的类名契约。

**最小打包文件**：`pyproject.toml`（setuptools 后端）：
```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "hone"
version = "0.1.0"
description = "Convert CSV to automatically nested JSON"
requires-python = ">=3.8"
dependencies = []

[project.scripts]
hone = "hone.__main__:main"

[tool.setuptools]
packages = ["hone", "hone.utils"]
```
`LICENSE` 用 MIT；`README.md` 至少含安装、命令行（文件输出 + `-` 标准输入/输出）、Python 模块、运行测试四方示例。

## 2. 接口与算法

### 2.1 公开接口（契约，先冻结）
```python
class Hone:
    DEFAULT_DELIMITERS = [",", "_", " "]
    def __init__(self, delimiters=None): ...      # None -> DEFAULT_DELIMITERS 的拷贝
    def get_schema(self, csv_filepath): ...        # 返回嵌套 dict：叶子值=原始列名
    def convert(self, csv_filepath, schema=None):  # schema 为 None 时自动生成
        ...                                        # 返回 [ {嵌套结构}, ... ]
    # 内部/辅助（命名贴近 UML，允许实现细节差异）
    def set_csv_filepath(self, path): ...          # 同时 self.csv = CSVUtils(path)
    def get_column_names(self): ...                # 复用 self.csv
    def get_data_rows(self): ...
    def generate_full_structure(self, column_names): ...
    def populate_structure_with_data(self, structure, column_names, data_rows): ...
    def get_leaves/get_nested_structure/get_valid_splits/... # 可按需
```
- `get_schema` 与 `convert` 通过 `set_csv_filepath` 创建**同一个** `CSVUtils` 实例，避免 stdin 被读两次。
- 叶子值语义：`get_schema` 的叶子值必须是**完整列名**（如 `"birth day"`），`convert` 再据此回填数据；不要提前落值。

### 2.2 CSVUtils 契约（M2 提供）
```python
class CSVUtils:
    def __init__(self, csv_filepath): ...
    @contextmanager
    def open_csv(self, mode="r", newline=""): ...    # '-' -> io.StringIO(共享的 stdin 缓存)
    def get_column_names(self): ...                  # 第一行 list[str]；空文件返回 []
    def get_data_rows(self): ...                     # 跳过表头后的 list[list[str]]，过滤空行
```
- 必须用 `csv.reader`（`quotechar='"'`, 默认 `doublequote=True`），**不要手写 split**，引号/双引号/逗号场景自动正确。
- 文件：`open(path, "r", newline="", encoding="utf-8")`（Windows 换行安全）；`-`：读取 `sys.stdin` 一次并缓存到**模块级** `_STDIN_CACHE`，之后每次 `open_csv` 都返回其 `StringIO` 副本，保证 `get_column_names`+`get_data_rows` 多次调用可重读。
- 无表头/空文件：`get_column_names()` 返回 `[]`、`get_data_rows()` 返回 `[]`，`convert` 返回 `[]`（不抛异常）。
- `json_utils.output_json(obj, path)`：`json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)`；`path == "-"` 写 `sys.stdout`，否则写 UTF-8 文件（末尾补 `\n`）。`parse_json_file(path)` 读回 dict/JSON。
- 修 `escape_quotes` 可保留为 UML 兼容辅助，但**不得二次转义**：引号转义全部交给 `csv`/`json` 模块。

### 2.3 自动嵌套 schema 算法（核心，M1）
在每一层，把「当前剩余后缀」按共享前缀分组；只有满足下面 4 条的切分才允许嵌套：
1. 切分点 `idx = rem.find(d)`，`d ∈ delimiters`，要求 `idx > 0` 且 `tail` 非空；
2. `head = rem[:idx]` **不是本层剩余列名之一**（保证 `a` 与 `a_b`、`adopted` 与 `adopted_since`、`reference` 与 `reference name` 保持平铺，叶子不能同时当内部节点）；
3. `head` 在本层**至少被 2 个列名共享**：存在 `other != rem` 使 `other.startswith(head + d)`（保证 `some '"quoted"' field"`、`age (years)`、`weight (kg)` 这类孤立前缀不产生多余嵌套）；
4. 多个候选时取**最早出现**的切分（`example_b` 的 `b_c_d` 必须先切 `b`，不能先切 `b_c`）。

伪代码：
```python
def generate_full_structure(self, column_names):
    return self._build(list(column_names), {c: c for c in column_names})

def _build(self, remainders, full_names):
    structure, groups, leaves = {}, {}, []
    R = set(remainders)
    for rem in remainders:
        split = self._first_valid_split(rem, R)
        if split is None:
            leaves.append(rem)
        else:
            head, tail, d = split
            groups.setdefault(head, []).append((tail, full_names[rem]))
    for rem in leaves:
        structure[rem] = full_names[rem]
    for head, members in groups.items():
        sub_rems, sub_full = [], {}
        for tail, full in members:
            if tail not in sub_full:          # 同层 key 去重
                sub_rems.append(tail); sub_full[tail] = full
        structure[head] = self._build(sub_rems, sub_full)
    return structure

def _first_valid_split(self, rem, R):
    best = None
    for d in self.delimiters:
        i = rem.find(d)
        if i <= 0 or i + len(d) >= len(rem): continue
        head, tail = rem[:i], rem[i+len(d):]
        if head in R: continue
        if not any(o != rem and o.startswith(head + d) for o in R): continue
        if best is None or i < best[0]:
            best = (i, head, tail, d)
    return None if best is None else best[1:]
```
预期自检（必须逐条对上）：
- `small_cats` → `birth` 下 `day/month/year`；`adopted`、`adopted_since` 平铺。
- `quotes_test` → `some '"quoted"' field"` 平铺（不做任何额外转义，csv 解析结果即列名）。
- `comma_test` → 两个怪异列名平铺。
- `example_b` → `a`、`a_b` 平铺，`b:{c:{d,e},d:{e,f}}`。
- `example_c` → `birth` 嵌套，`reference`/`reference name` 平铺。

### 2.4 回填
```python
def populate_structure_with_data(self, structure, column_names, data_rows):
    idx = {name: i for i, name in enumerate(column_names)}
    def fill(node, row):
        if isinstance(node, dict): return {k: fill(v, row) for k, v in node.items()}
        if node not in idx: raise ValueError(f"schema leaf {node!r} not in CSV columns")
        return row[idx[node]] if idx[node] < len(row) else ""
    return [fill(structure, row) for row in data_rows]
```
- 缺失单元格补 `""`；空值保留 `""`；数据/表头行数不齐不崩溃。

## 3. CLI（`hone/__main__.py`，M3）
```
python -m hone [-h] [-d [DELIMITERS]] [-s [SCHEMA]] csv_filepath json_filepath
```
- 位置参数 `csv_filepath`、`json_filepath`，`-` 分别代表 stdin/stdout（help 文案照 `docs/README.md`）。
- `-d/--delimiters`：`nargs="?", default=None`，`ast.literal_eval` 解析为 `list[str]`（如 `-d "['_', ' ']"`），失败→stderr + 退出码 2；None 用默认 `[',', '_', ' ']`。
- `-s/--schema`：`nargs="?", default=None`，`json.loads` 得到嵌套 dict，失败→stderr + 退出码 2；None 走自动 schema。
- 流程：`Hone(delimiters).convert(csv_filepath, schema=schema)` → `output_json(result, json_filepath)`；文件输出用 `indent=2, sort_keys=True`，stdout 同头部 JSON + 末尾换行。
- 退出码：`0` 成功；`2` 参数/`-d`/`-s` 解析错误（argparse 原生即 2）；`1` 文件不存在、编码/IO、schema 与列名不匹配等运行时错误（捕获后打印一行 `hone: error: ...` 到 stderr，不吐 traceback）。
- `main(argv=None) -> int`，`if __name__ == "__main__": raise SystemExit(main())`；同时供 `[project.scripts]` 使用。
- 必须可：`python -m hone examples/example_a.csv out.json`、`python -m hone - - < examples/example_a.csv`、`python -m hone examples/example_a.csv -`。

## 4. 验收用例（含负责人与产出路径）

| # | 用例 | 判定 | 实现人 | 测试产出 |
|---|---|---|---|---|
| AC1 | 导入：`python -c "import hone; from hone.hone import Hone"` | 无异常，`hone.Hone is Hone` | M1/M3 | `tests/test_import.py` |
| AC2 | `CSVUtils` 表头/数据行（含引号、逗号、`-` 缓存） | 与人工期望一致 | M2 | `tests/test_csv_utils.py` |
| AC3 | `Hone().get_schema('data_file/small_cats_dataset/dataset.csv')` | `json.loads` 后 **等于** `nested_schema.json` | M1 | `tests/test_hone_schema.py` |
| AC4 | 三组 `data_file/*/dataset.csv` 自动转换 | `json.loads` 后等于各自 `nested_dataset.json`（**语义比较**，见风险 R3） | M1 | `tests/test_convert_datasets.py` |
| AC5 | 指定 schema：`get_schema` 结果作 `convert(..., schema=...)`；schema 与 `nested_schema.json` 一致 | 输出等于 `nested_dataset.json` | M1/M4 | `tests/test_schema_override.py` |
| AC6 | `examples/example_a/b/c.csv` | 语义等于 `examples/example_*.json`；`example_b` 验证 `a`/`a_b` 平铺与 `b` 双层嵌套（忽略 README 中 `"f":"1"` 笔误，以实际 csv 数据 `12` 为准） | M4 | `tests/test_examples.py` |
| AC7 | 引号/逗号/空值：`quotes_test`、`comma_test`、含空单元格临时 csv | 无异常、键名与值精确匹配 | M4 | `tests/test_special_csv.py` |
| AC8 | CLI 文件输出 | `tmp/out.json` 语义等于 `examples/example_a.json`，且可用 `json.dumps(..., indent=2, sort_keys=True)` 复核 | M3 | `tests/test_cli.py` |
| AC9 | CLI `-`：`python -m hone examples/example_a.csv -`、`... - - < examples/example_a.csv` | stdout 可被 `json.loads`，等于期望结构 | M3 | `tests/test_cli.py` |
| AC10 | `python -m hone --help` | 含两个位置参数与 `-d/-s` 说明，退出 0 | M3 | `tests/test_cli.py` |
| AC11 | `pip install .`（venv 或 `--target tmp/site`） | 安装成功；`python -c "import hone"`；`hone --help` 可用；`python -m hone` 可用 | M3 | `tests/test_packaging.py`（无网络时用 `--no-build-isolation`，见 R5） |
| AC12 | 冒烟：`python -m unittest discover -s tests -v` 全绿；`python examples/demo.py` 可运行 | 0 failure；样例文件 `git status` 无改动 | M4 + 全员 | 最终验收命令 |

**统一验证命令（每人自测后组内共享）**
```bash
python -m unittest discover -s tests -v
python -m hone examples/example_a.csv - | python -c "import json,sys; json.load(sys.stdin); print('ok')"
python -m hone - - < examples/example_b.csv
python -c "from hone.hone import Hone; import json; print(json.dumps(Hone().get_schema('data_file/small_cats_dataset/dataset.csv'), indent=2, sort_keys=True))"
pip install . && python -c "import hone, hone.hone; print('installed ok')"
```

## 5. 4 人分工与交付顺序
- **M1 core/schema**：`hone/hone.py`。先按 §2.1~2.4 实现并自测 AC3/AC4/AC5；提交前跑 `_build` 对 6 个样例的手工断言。
- **M2 utils**：`hone/utils/*`。先冻结 CSVUtils/JSONUtils 契约（§2.2）供 M1/M3 import；自测 AC2、stdin 缓存与引号解析。
- **M3 cli/packaging**：`hone/__init__.py`、`hone/__main__.py`、`pyproject.toml`、`README.md`、`LICENSE`；兼任集成协调。自测 AC1/AC8~AC11。
- **M4 tests/docs 验证**：`tests/*`。在契约冻结后先写红测试，集成后转绿；维护 AC 清单与验证命令；负责 AC6/AC7/AC12。
- 依赖顺序：M2 冻结契约 → M1 实现 core → M3 接 CLI/打包 → M4 全量回归；M4 可先用契约写测试，不被阻塞。

## 6. 风险点与对策
- **R1 stdin 被读两次**：`get_schema`/`get_data_rows` 复用同一 `CSVUtils`，且 stdin 用模块级缓存；AC9 覆盖。
- **R2 嵌套算法误拆**：`a` vs `a_b`、`adopted` vs `adopted_since`、孤立前缀（`some ...`、`age (years)`）必须按 §2.3 规则 2/3 保持平铺；`b_c_d` 必须先切 `b`（规则 4）。M1 需对这 6 个具体列名写断言。
- **R3 文本比较 vs 语义比较**：`quotes_test/nested_dataset.json` 未按 `sort_keys` 排序，禁止逐字节比较；AC3~AC9 一律 `json.loads` 后比较。CLI 文本仅在结构明确时允许 `indent=2, sort_keys=True` 断言。
- **R4 引号/转义**：不要手写 CSV 解析或二次 `escape_quotes`；`comma_test` 的键 `"test","ing"`、` "beep"""` 必须由 `csv.reader` 原样得到。
- **R5 离线 pip 安装**：`pip install .` 可能触发构建隔离联网；测试回退 `python -m pip install . --no-build-isolation`（或 `--target`），环境无 setuptools 时才降级 setup.py。
- **R6 多分隔符/同 head 冲突**：同一 head 由不同分隔符产生同尾后缀时按“首个出现的分隔符保留、重复 key 去重”；极端用例不作为验收硬要求，实现内注释说明。
- **R7 单成员分组**：若某前缀最终仅 1 个成员，建议不生成单子节点嵌套（保持平铺），但需先跑 AC3~AC6 确认不影响期望输出。
- **R8 Windows 路径/编码**：统一 `pathlib` + `encoding="utf-8"` + `newline=""`；测试用 `__file__` 推仓库根，不用相对 CWD。
- **R9 顺序稳定性**：结构插入顺序无关紧要（输出 `sort_keys=True`）；测试与断言不要依赖 dict 顺序。
- **R10 包名冲突**：安装名为 `hone`，仅本地/虚拟环境安装验证，不发布 PyPI。

## 7. Definition of Done
1. `hone` 可 `import`，`Hone` 位于 `hone.hone`，公开方法签名与 §2.1 一致；
2. `get_schema` 与 `convert` 对 3 组 data_file + 3 组 examples 全部语义通过；
3. CLI 支持文件与 `-` 标准流，`-d`/`-s` 解析正确，`indent=2`/`sort_keys=True`，退出码 0/1/2 符合定义；
4. `python -m hone` 与 `pip install .` 后 `hone` 命令均可用；
5. `python -m unittest discover -s tests -v` 全绿；样例文件零改动；README 命令可复制运行。


## 第1轮 · admin-3c921dfcf1344cb09955f72589931163
【R1 Recorder 草案】完整计划已写入输出板（含接口契约、算法伪码、验收表、分工与风险），摘要如下，请各位重点审 3 个决策点：

1) 仓库布局：在含 docs/data_file/examples 的仓库根新增 hone/{__init__.py,hone.py,__main__.py,utils/{__init__,csv_utils,json_utils,test_utils}.py}、tests/、README.md、pyproject.toml；四人独占路径：A=hone/hone.py+__init__+schema/convert测试；B=hone/utils/*+csv单测；C=__main__.py+pyproject+CLI测试；D=tests/__init__+examples集成测试+README+.gitignore。

2) 核心算法：默认 delimiters=[',','_',' ']；列名先过 csv.reader，再 replace('""','"')；自动嵌套的合法切分必须满足——每个前缀 (a) 不是现有列名（防 a_b→a、adopted_since→adopted、reference name→reference），且 (b) 至少被 2 列共享（防 age (years)、some 'quoted"' field" 被切）；多条合法切分按段数降序、分隔符顺序取第一条。schema 叶子值存原始列名，populate 时按 column_names.index 填行；指定 nested_schema.json 走同一 populate。CSVUtils 一次性缓存整表，保证 convert 先取列名再取数据时 stdin('-') 不被读空。

3) CLI：argparse 两位置参数 csv_filepath/json_filepath，'-' 表示 stdin/stdout；-d 用 ast.literal_eval 解析 list[str]；-s 用 json.loads 要求 dict；输出 json.dump(indent=2, sort_keys=True)+换行；成功0，运行错误1，argparse错误2；pyproject 配 hone=hone.__main__:main，并验证 pip install . / wheel 后 import hone 与 python -m hone。

验收以 json.load 深度比较：三组 dataset.csv 对应 nested_dataset.json；small_cats 指定 schema 同结果；example_b 断言 a/a_b 叶子 + b.c.d/e、b.d.e/f（注意 examples/README 第二行 "f":"1" 是笔误，实际应为 "12"）；CLI 文件/stdout/stdin、-d/-s、错误码；全量 unittest；样例零改动。

风险：前缀规则、escape 范围、stdin 缓存、data_rows.csv 单行按表头语义（以 dataset.csv 验收）、嵌套路径冲突回退、打包 packages.find 收录 hone.utils。

请确认：① 前缀判据是否认可；② data_rows.csv 仅单行、按“首行表头”会得到0行的说明是否接受；③ 建议合并顺序 B→A→C→D、是否用独立 worktree。R2 我据此定稿。
