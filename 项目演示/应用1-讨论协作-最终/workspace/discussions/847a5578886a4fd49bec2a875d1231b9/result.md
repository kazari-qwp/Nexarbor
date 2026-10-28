# hone 实现计划（最终定稿 / Recorder R2，含全体 R2 修正）

> 本文为执行组最终任务说明，以上轮 R2 三份反馈为准已并入修正。仓库根 = 包含 `docs/`、`data_file/`、`examples/` 的目录（`workspace/task`，执行组用自身 `git.workspace` 初始化）。样例/文档字节级保持原样，只新增 `hone/`、`tests/`、`README.md`、`pyproject.toml`、`LICENSE`、`.gitignore`。核心仅标准库，Python ≥3.8。

## 0. 冻结结论（最高优先级）

1. **唯一 CSV 解析器 = `csv.reader` 默认方言**（`delimiter=','`、`quotechar='"'`、`doublequote=True`、`skipinitialspace=False`）+ `newline=''`、`encoding='utf-8'`。解析结果**原样使用**，禁止任何 `strip/replace/unescape/escape` 进入转换链路。`comma_test` 期望键/值即 csv 模块一次解析结果：列名 `['"test","ing"', ' "beep"""']`，数据 `['"1', '"2']`；`escape_quotes` 仅保留 UML 兼容签名，**禁止调用**。
2. **自动嵌套切分 = 每层“最左合法切分”**。合法条件：head、tail 非空；`head` 不在**当前递归层**剩余列名集合 R 中；head 被本层至少 2 个剩余项以 `head + 同一 delimiter` 共享。多个候选取 `rem.find(d)` 最小者，等 idx 按 `self.delimiters` 顺序。**不得用“段数降序/最长前缀”**，否则 `b_c_d` 会被拆成 `b_c.d` 而非期望 `b.c.d`。本层所有 groups 都要递归，不能只处理一个 prefix。
3. **stdin 只读一次**：`convert` 内只构造/复用一个 `CSVUtils`；`CSVUtils` 实例内懒解析 `_rows` 缓存整表，`get_column_names/get_data_rows/get_all_rows` 都从缓存切片。
4. **验收一律 `json.load` 语义比较**，不做文本 diff；仅 CLI 额外验证输出格式 `indent=2, sort_keys=True, ensure_ascii=False` + 末尾换行。

## 1. 文件布局与归属（路径互斥）

```
hone/__init__.py                 # A: from .hone import Hone; __all__=["Hone"]; __version__="0.1.0"
hone/hone.py                     # A: Hone 全部实现（schema/populate/convert）
hone/__main__.py                 # C: argparse CLI；main(argv=None)->int
hone/utils/__init__.py           # B
hone/utils/csv_utils.py          # B: CSVUtils + parse_csv_file + escape_quotes（兼容保留，不调用）
hone/utils/json_utils.py         # B: output_json / parse_json_file
hone/utils/test_utils.py         # D: 测试辅助（load/compare/make_temp_csv）
tests/__init__.py                # D
tests/test_schema.py             # A: 导入 + 自动 schema/切分规则
tests/test_convert.py            # A: convert/populate/指定 schema/三组 data_file
tests/test_csv_utils.py          # B: 列名、数据行、get_all_rows、缓存、`-`
tests/test_special_csv.py        # B: comma/quotes 精确断言、空值
tests/test_cli.py                # C: 文件/stdout/stdin/-d/-s/退出码/python -m hone
tests/test_packaging.py          # C: wheel 安装导入冒烟（可 skip）
tests/test_examples.py           # D: examples a/b/c、demo.py、样例零改动
README.md                        # D: 安装、CLI 文件与 stdout/stdin 示例、Python API、测试、行为说明
pyproject.toml                   # C: setuptools + console script
LICENSE                          # C: MIT
.gitignore                       # D: __pycache__/、*.py[cod]、build/、dist/、*.egg-info/、.venv/
```

`pyproject.toml`：`[build-system] requires=["setuptools>=61"]`、`build-backend="setuptools.build_meta"`；`[project] name="hone" version="0.1.0" requires-python=">=3.8" dependencies=[] readme="README.md" license={text="MIT"}`；`[project.scripts] hone="hone.__main__:main"`；`[tool.setuptools.packages.find] include=["hone*"]`（确保 `hone.utils` 入包）。不打包 docs/data_file/examples。

## 2. 冻结接口

```python
class Hone:
    DEFAULT_DELIMITERS = [',', '_', ' ']
    def __init__(self, delimiters=None)          # None -> DEFAULT 拷贝；list/tuple[str] 且元素非空，否则 ValueError
    def set_csv_filepath(self, csv_filepath)     # 同路径且已有 self.csv 时复用，否则新建 CSVUtils
    def get_schema(self, csv_filepath) -> dict
    def convert(self, csv_filepath, schema=None) -> list[dict]   # schema: None|dict|JSON str
    def generate_full_structure(self, column_names) -> dict
    def populate_structure_with_data(self, structure, column_names, data_rows) -> list[dict]
    def get_nested_structure(self, parent_structure) -> dict      # UML 兼容，不进主链路
    def get_leaves(self, structure, path=None, result=None) -> list[tuple[list[str], str]]
    def get_valid_splits(self, column_name) -> list[list[str]]    # 返回全部合法候选，按优先级排序
    def get_split_suffix(self, split, column_name) -> str
    def clean_split(self, split)                  # 仅处理空段/段数；不得加“首字符字母数字”等启发式
    def is_valid_prefix(self, prefix, base) -> bool
    def escape_quotes(self, string) -> str        # 兼容保留；转换链路禁止调用

class CSVUtils:
    def __init__(self, csv_filepath)              # '-' 表示 stdin
    def open_csv(self, mode='r', newline='')      # 文件用 open(..., encoding='utf-8', newline='')；'-' 用 sys.stdin 且不关闭
    def get_column_names(self) -> list[str]       # 首条记录；空文件 []
    def get_data_rows(self) -> list[list[str]]    # 首条之后，过滤 [] 空行
    def get_all_rows(self) -> list[list[str]]     # 全部记录（含首行），供 fixture 覆盖
    # 内部 _read_all()：首次访问解析一次并缓存 self._rows

def output_json(json_struct, json_filepath)       # indent=2, sort_keys=True, ensure_ascii=False；末尾 '\n'；'-'->stdout
def parse_json_file(json_filepath)                # '-'->stdin
def parse_csv_file(csv_filepath)                  # 全部记录（含首行）
```

`data_rows.csv` 语义已冻结：首行恒为表头，因此单独对 `data_rows.csv` 调 `get_data_rows()` 返回 `[]` 是**正确行为**，测试需显式断言并注释；三组数据转换验收一律用 `dataset.csv`。为避免 fixture 死文件，B 用 `get_all_rows()` 断言：
`get_all_rows('column_names.csv') == get_column_names('dataset.csv')`，`get_all_rows('data_rows.csv') == get_data_rows('dataset.csv')`。

## 3. 核心算法

### 3.1 读取与值语义

- 列名/数据单元格均为字符串，空单元格 `""`，不做类型推断；重复列名首次为准；行短补 `""`，超长忽略多余列。
- 任何引号/逗号/空值场景全部交给 csv 模块；实现前先跑探针并把结果与 fixture 对齐：
  `python -c "import csv,pprint; pprint.pprint(list(csv.reader(open('data_file/comma_test/dataset.csv',newline='',encoding='utf-8'))))"`。

### 3.2 自动生成 schema（递归 + 分组）

```
def generate_full_structure(self, column_names):
    remainders = {}
    for c in column_names: remainders.setdefault(c, c)
    return self._build(remainders)

def _build(self, remainders):                 # dict: rem -> 原始完整列名
    R = set(remainders)
    result, groups, leaves = {}, {}, []
    for rem, full in remainders.items():
        split = self._first_valid_split(rem, R)
        if split is None:
            leaves.append((rem, full))
        else:
            head, tail, delim = split
            groups.setdefault(head, []).append((tail, full))
    for rem, full in leaves:
        result.setdefault(rem, full)          # 同层 key 冲突：保留首个
    for head, members in groups.items():
        sub = {}
        for tail, full in members:
            sub.setdefault(tail, full)        # 同层去重，保留首个
        result[head] = self._build(sub)       # 本层所有 groups 都递归
    return result

def _first_valid_split(self, rem, R):
    best = None
    for idx_d, d in enumerate(self.delimiters):
        i = rem.find(d)
        if i <= 0: continue
        head, tail = rem[:i], rem[i+len(d):]
        if not tail: continue
        if head in R: continue                # 规则1：head 是本层列名 -> 不可当对象
        if not any(o != rem and o.startswith(head + d) for o in R):
            continue                          # 规则2：同层 ≥2 项共享 head+d
        key = (i, idx_d, d)
        if best is None or key < best[0]: best = (key, head, tail, d)
    return None if best is None else best[1:]
```

校验：
- `a`/`a_b`、`adopted`/`adopted_since`、`reference`/`reference name`：head 在 R 中 → 平铺。
- `age (years)`、`weight (kg)`、`some '"quoted"' field"`、comma 怪异列名：head 无同层共享 → 平铺。
- `birth day/month/year` → `birth` 组；`b_c_d` 取 idx=1 的 `b`，递归后 `b.c.d`、`b.c.e`、`b.d.e`、`b.d.f`。
- 多个独立前缀（如 `birth` 与 `contact`）会各自成组并全部递归，不会只嵌套一个。
- `get_valid_splits` 用 `R=set(self.column_names)` 返回全部合法候选；`is_valid_prefix` 实现规则1+2；`clean_split` 只对空段/段数做校验。以上为兼容/测试入口，主流程以 `_build` 为准。

### 3.3 回填与 convert

```
def populate_structure_with_data(structure, column_names, data_rows):
    index = {name: i for i, name in enumerate(column_names)}
    leaves = self.get_leaves(structure)       # [(path_list, source_column_name)]
    out = []
    for row in data_rows:
        obj = {}
        for path, col in leaves:
            if col not in index:
                raise ValueError(f"schema column not found in CSV: {col!r}")
            value = row[index[col]] if index[col] < len(row) else ""
            node = obj
            for key in path[:-1]: node = node.setdefault(key, {})
            node[path[-1]] = value
        out.append(obj)
    return out

def convert(self, csv_filepath, schema=None):
    self.set_csv_filepath(csv_filepath)
    column_names = self.csv.get_column_names()
    data_rows = self.csv.get_data_rows()
    if schema is None:
        schema = self.generate_full_structure(column_names)
    elif isinstance(schema, str):
        schema = json.loads(schema)           # 防御性；CLI 已传 dict
    return self.populate_structure_with_data(schema, column_names, data_rows)

def get_schema(self, csv_filepath):
    self.set_csv_filepath(csv_filepath)
    return self.generate_full_structure(self.csv.get_column_names())
```

`schema` 叶子值必须是**完整原始列名**（不是输出键名）；`-s` 传入的 `nested_schema.json` 满足。`set_csv_filepath` 同路径复用同一 `CSVUtils`，保证 `'-'` 下 `get_schema('-')` 后再 `convert('-')` 仍可读。

## 4. CLI（hone/__main__.py）

```
usage: hone [-h] [-d [DELIMITERS]] [-s [SCHEMA]] csv_filepath json_filepath
```

- 位置参数 `csv_filepath`、`json_filepath`；`-` 分别 stdin/stdout。help 与 docs/README 对齐。
- `-d/--delimiters`：`nargs='?'`；`ast.literal_eval` 优先，失败回退 `json.loads`；必须得到非空 `list[str]`，否则 `parser.error` → 退出码 2；None 用默认。
- `-s/--schema`：`nargs='?'`；`json.loads` 且必须为 dict（`[]`/非 JSON 均参数错误，退出码 2）；None 自动 schema。
- 主流程：`args=parse_args()` → `Hone(args.delimiters).convert(args.csv_filepath, args.schema)` → `output_json(result, args.json_filepath)`。
- 输出：`json.dump(..., indent=2, sort_keys=True, ensure_ascii=False)` + 末尾 `'\n'`；stdout 只写 JSON，不混日志。
- 退出码：成功 0；argparse/`-d`/`-s` 错误 2；运行期错误（文件不存在、编码/IO、schema 缺列、JSON 文件异常）捕获后 stderr 单行 `hone: error: ...`，返回 1，不打 traceback。
- `main(argv=None)->int`；`if __name__ == "__main__": raise SystemExit(main())`；`python -m hone` 与安装后 `hone` 行为一致。

## 5. 验收清单（负责人 / 产出 / 判定）

| # | 验收项 | 负责人 | 产出/判定 |
|---|--------|--------|-----------|
| AC1 | 可导入：`import hone`、`from hone.hone import Hone`、`hone.Hone is Hone` | A/C | `tests/test_schema.py` 导入断言；无异常 |
| AC2 | CSVUtils 列名/数据行/空行/缓存/`-`；`get_all_rows` 覆盖 `column_names.csv`、`data_rows.csv` | B | `tests/test_csv_utils.py`；逐字段相等，`get_data_rows(data_rows.csv)==[]` 显式断言并注释 |
| AC3 | small_cats 自动 schema == `nested_schema.json` | A | `tests/test_schema.py`；dict 相等 |
| AC4 | 三组 `data_file/*/dataset.csv` 自动转换 == 各自 `nested_dataset.json` | A | `tests/test_convert.py`；`json.load` 语义相等 |
| AC5 | 指定 `nested_schema.json` 转换 == `nested_dataset.json`；`get_schema` 结果再传回也一致 | A | 同上 |
| AC6 | comma_test 精确断言列名/数据行/输出 | B+A | `tests/test_special_csv.py`；表头 `['"test","ing"', ' "beep"""']`、行 `['"1','"2']`、输出等 fixture |
| AC7 | quotes_test 单双引号/N/A/空值；临时 CSV 空单元格输出 `""` | B/D | `tests/test_special_csv.py` + `tests/test_examples.py` |
| AC8 | example_b：`a`、`a_b` 叶子；`b.c.{d,e}`、`b.d.{e,f}`；第二行 `b.d.f=="12"` | A/D | 显式期望结构；README 的 `"1"` 是笔误，不读该片段、不改样例 |
| AC9 | example_a/c 与 examples/README 期望一致；`python examples/demo.py` 可跑 | D | `tests/test_examples.py` |
| AC10 | CLI 文件输出 | C | `tests/test_cli.py`；解析相等 + 文本满足 indent=2/sort_keys |
| AC11 | CLI stdout/stdin | C | `python -m hone examples/example_a.csv -`、`python -m hone - - < examples/example_b.csv`；stdout 可 `json.loads` 且等于文件输入 |
| AC12 | `python -m hone --help` | C | 退出 0，含两位置参数与 `-d/-s` |
| AC13 | 错误码 | C | 不存在文件→1；`-d "not a list"`、`-s "{bad}"`、`-s "[]"`→2；stderr 有 `hone: error:`；运行错误无 traceback |
| AC14 | 打包/安装 | C | venv 中 `python -m pip install . --no-build-isolation` → `import hone`、`hone --help`、`python -m hone`；`pip wheel . --no-build-isolation -w dist` 产物可安装并导入 |
| AC15 | 全量测试与零改动 | D | `python -m unittest discover -s tests -t . -v` 全绿；`python examples/demo.py`；`git diff --exit-code HEAD -- docs data_file examples` 为空、`git status` 干净 |

统一自测命令（各成员完成后贴“命令+预期+实际”到组内）：
```bash
python -m unittest discover -s tests -t . -v
python -m hone examples/example_b.csv -
python -m hone - - < examples/example_c.csv
python -c "import hone,json; print(json.dumps(hone.Hone().get_schema('data_file/small_cats_dataset/dataset.csv'), indent=2, sort_keys=True))"
python examples/demo.py
python -m pip wheel . --no-build-isolation -w dist
```

## 6. 四人分工与 Git 整合

| 成员 | 职责 | 独占路径 | 自测 |
|------|------|----------|------|
| **A core/schema** | `Hone` 全部方法、自动 schema、populate/convert | `hone/hone.py`、`hone/__init__.py`、`tests/test_schema.py`、`tests/test_convert.py` | AC1/3/4/5/8 |
| **B utils/CSV** | `CSVUtils` 缓存/标准流/`get_all_rows`、JSON 输出、特殊 CSV | `hone/utils/**`、`tests/test_csv_utils.py`、`tests/test_special_csv.py` | AC2/6/7（CSV 侧） |
| **C CLI/打包/集成协调** | argparse、退出码、`-d/-s`、pyproject、LICENSE、打包冒烟、合并 | `hone/__main__.py`、`pyproject.toml`、`LICENSE`、`tests/test_cli.py`、`tests/test_packaging.py` | AC10–AC14；负责合并全量 |
| **D 测试/文档/夹具** | 集成验收、examples、README、.gitignore、样例零改动、最终回归 | `tests/__init__.py`、`tests/test_examples.py`、`hone/utils/test_utils.py`、`README.md`、`.gitignore` | AC7（examples 侧）/9/15 |

规则：
1. 执行组用 `git.workspace` 初始化 git，先提交 pristine 基线（`docs/ data_file/ examples/ INPUTS.md`，逐字节不变）；不强制独立 worktree，普通分支/共享工作树即可，但**每人只 `git add` 自己独占路径**。
2. 建议 A 先提交可 import 的骨架（类 + 方法签名 + `NotImplementedError`），C/D 按冻结契约并行；B 先落 utils，随后 A→C→D 集成。
3. 分支 `feat/core`、`feat/utils`、`feat/cli-packaging`、`feat/tests-docs`；提交信息 `feat(core): ...` 等。冲突只在 tests/docs 边缘，由 C 裁决；签名争议以本文第 2/3 节为准。
4. Definition of Done：AC1–AC15 全绿并附输出；`pip install .` 成功；`import hone`/`python -m hone`/安装后 `hone` 均可用；README 含“文件输出”与“stdout/stdin”两条可复制运行示例；`docs/ data_file/ examples/` 零改动。

## 7. 风险点与对策

1. **二次反转义（最高危）**：任何 `replace('""','"')`/`escape_quotes` 进链路都会破坏 comma_test/quotes_test；AC6 精确断言为闸门；实现前先跑 csv 探针。
2. **切分选择错误**：用“段数降序/最长前缀”会使 `b_c_d` 变成 `b_c.d`；必须最左合法切分；AC4/AC8 锁定。
3. **过度拆分/冲突**：只判“非列名”会拆 `age (years)`；只判“共享”会嵌 `a_b`；两条件缺一不可，且均用**当前递归层**集合、同一 delimiter。
4. **多 prefix 漏分组**：本层所有合法 groups 都要递归，只有无合法切分的才是叶子；否则含 `birth`+`contact` 的 CSV 会少嵌套。
5. **stdin 二次读取**：`convert` 单 `CSVUtils` + 实例缓存；AC11 覆盖；不依赖模块级全局缓存。
6. **文本 diff 假红**：fixture 缩进/键序与 `sort_keys=True` 不同；一律 `json.load` 语义比较，格式只在 CLI 输出后回比。
7. **fixture 死文件**：`data_rows.csv` 的 `get_data_rows()==[]` 是定义正确行为，用 `get_all_rows()` 覆盖其内容；不为其加特殊分支。
8. **-d/-s 解析**：`-d` 只接受一个字符串参数，`ast.literal_eval` 后必须非空 `list[str]`；`-s` 必须 dict；参数错误 2、运行错误 1，不打 traceback。
9. **离线打包**：构建隔离可能联网，统一 `--no-build-isolation` 回退；`packages.find include=["hone*"]` 收录 `hone.utils`。
10. **示例笔误**：`examples/README.md` 中 example_b 第二行 `b.d.f` 写作 `"1"`，与输入 `12` 矛盾；以 `"12"` 为验收，测试注释说明，**不修改样例**。
11. **编码/路径**：UTF-8、`newline=''`；测试用 `ROOT = pathlib.Path(__file__).resolve().parents[1]`，CLI 用 `[sys.executable, "-m", "hone", ...]`，不依赖 CWD。
12. **职责越界**：只改自己路径；D 最后用 `git diff`/`git status` 证明样例与文档零改动。
