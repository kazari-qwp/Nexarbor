# CONTRACT.md - hone FINAL plan sections 2/3 (frozen)

## 2. 文件/模块布局与公共接口契约

### 2.1 布局与唯一文件所有权（他人只能提 issue，不得直接改）
```
$P/
├─ CONTRACT.md                   # 阶段0 A 落盘（= 本文件 §2/§3），冻结
├─ pyproject.toml                # C
├─ LICENSE                       # C（MIT）
├─ README.md                     # D
├─ RELEASE_NOTES.md              # D（发布时）
├─ scripts/acceptance.py         # D：G1–G13 一键验收，打印 PASS/FAIL 表
├─ hone/
│  ├─ __init__.py                # A：from .hone import Hone; __all__=["Hone"]; __version__="1.0.0"
│  ├─ hone.py                    # A：Hone 全部方法
│  ├─ __main__.py                # C：main(argv=None)->int；if __name__=="__main__": sys.exit(main())
│  └─ utils/
│     ├─ __init__.py             # 阶段0 A 建空壳；此后 B 唯一 owner（导出 CSVUtils/parse_csv_file/output_json/parse_json_file）
│     ├─ csv_utils.py            # B
│     ├─ json_utils.py           # B
│     └─ test_utils.py           # B
├─ tests/
│  ├─ __init__.py                # 阶段0 A 建（含 task_root()/fixture 解析 helper）；此后 D 唯一 owner
│  ├─ fixtures/                  # 阶段0 A 建：只读副本 + MANIFEST.sha256；此后 D owner
│  │  └─ data_file/{comma_test,quotes_test,small_cats_dataset}/**（dataset.csv、column_names.csv、data_rows.csv、nested_dataset.json、nested_schema.json）
│  ├─ test_hone_core.py          # A
│  ├─ test_utils_csvjson.py      # B
│  ├─ test_cli_packaging.py      # C
│  ├─ test_golden_samples.py     # D
│  └─ test_boundaries.py         # D（§2.4 + 边界/编码/多字符分隔符）
├─ examples/                     # C 维护 demo.py/demo.sh；example_a|b|c.csv 为阶段0 A 的只读副本（字节一致）
└─ .worktrees/{a,b,c,d}/         # 4 人各自 worktree（.gitignore）
```
> 架构文档中的 `hone/test/` 由根 `tests/` **取代**（不建双份）。`tests/fixtures/**` 与 `examples/*.csv` 副本均**只读**：任何测试不得改写。

### 2.2 `hone.hone.Hone` 契约（签名逐字固定；模块首行 `from __future__ import annotations`）
```python
class Hone:
    DEFAULT_DELIMITERS = [',', '_', ' ']      # 类属性；实例 self.delimiters 为其副本

    def __init__(self, delimiters=None):
        # None → list(DEFAULT_DELIMITERS)；否则必须是非空 list[str]，否则 ValueError
        # 初始化 self.delimiters, self.csv_filepath=None, self.csv=None, self.column_names=[]

    def set_csv_filepath(self, csv_filepath) -> None    # 存路径（"-" 合法）；self.csv=CSVUtils(p)；self.column_names=self.csv.get_column_names()
    def convert(self, csv_filepath, schema=None) -> list[dict]     # csv_filepath 必填（不得为 None，None→ValueError）
    def get_schema(self, csv_filepath) -> dict          # csv_filepath 必填
    def generate_full_structure(self, column_names) -> dict
    def get_nested_structure(self, parent_structure) -> dict
    def populate_structure_with_data(self, structure, column_names, data_rows) -> list[dict]
    def get_leaves(self, structure, path=(), result=None) -> dict[tuple[str, ...], str]
    def get_valid_splits(self, column_name) -> list[list[str]]
    def get_split_suffix(self, split, column_name) -> str
    def clean_split(self, split) -> list[str]
    def is_valid_prefix(self, prefix, base) -> bool
    def escape_quotes(self, string) -> str
```
语义（逐条实现，docstring 同步抄写）：
- **convert**：`set_csv_filepath(csv_filepath)`；`cols=self.column_names`，`rows=self.csv.get_data_rows()`（**共享同一缓存，禁止再开文件**）；`schema is None` → `structure=self.generate_full_structure(cols)`；`schema` 为 str 先 `json.loads`；否则 `structure=schema`；`return self.populate_structure_with_data(structure, cols, rows)`。**返回 list（每数据行一个 dict，行序=CSV 行序），叶子值一律 str（不做类型推断）**。
- **get_schema(csv_filepath)**：`set_csv_filepath` → `return copy.deepcopy(self.generate_full_structure(self.column_names))`。**叶子值 = 完整原始列名**，与 `{"birth":{"year":"birth year",...}}` 形状一致。
- **generate_full_structure(column_names)**：按 §3 建树，返回**单条记录**的嵌套 dict，**叶子值 = 该叶子的完整原始列名**（无 None 叶子）。
- **get_nested_structure(parent_structure)**：`copy.deepcopy` 并归一化为纯嵌套 dict，**保留字符串叶子**（不擦成 None、不改键名、不改叶子值）；不修改入参。
- **populate_structure_with_data(structure, column_names, data_rows)**：`idx={c:i for i,c in enumerate(column_names)}`（重复表头后者覆盖）；每行 `copy.deepcopy(structure)` 后递归填充：dict→递归；str 叶子→`i=idx.get(leaf)`：`i is not None 且 i < len(row)` → `row[i]`；**`i` 不存在（schema 引用缺失列）或 `i >= len(row)`（行短）→ 该键从该行 dict 中省略**；多余单元格丢弃。
- **get_leaves(structure, path=(), result=None)**：返回 **dict** `{(路径元组): 叶子字符串}`，路径含叶子键本身，如 `{(("birth","day"),): ...}` 写作 `{("birth","day"): "birth day", ("name",): "name"}`；`result` 默认 `None`（内部新建 `{}`），不修改入参。
- **get_valid_splits(column_name)**：**纯语法候选**（不依赖表头）：对每个 `d in self.delimiters`（按顺序）、`column_name` 中 `d` 的每个出现位置 `i`，`p=column_name[:i]`，`rem=column_name[i+len(d):]`，`p.strip()` 与 `rem.strip()` 均非空 → 候选 `[p, rem]`；按「分隔符顺序 → 位置从左到右」返回 `list[list[str]]`；无候选 → `[]`。**语义过滤（共享前缀/完整列名冲突）不在本方法内，交由 §3.2 `choose` 完成**（避免依赖表头上下文、可独立单测）。
- **get_split_suffix(split, column_name)**：`split` 为 `get_valid_splits` 的返回项；直接 `return split[1]`（`len(split) != 2` → `ValueError`）；不再对 `column_name` 做可拼回校验（保留参数以符合任务签名）。
- **clean_split(split)**：输入 list[str]（一次切分结果）：每段 `strip()`、丢弃空段，返回 list[str]；输入 str 时先按任一 `self.delimiters` 切成段。全空 → `[]`。
- **is_valid_prefix(prefix, base)**：**纯字符串谓词**：`base == prefix` 或存在 `d in self.delimiters` 使 `base.startswith(prefix + d)` → True；否则 False。（`("a","a_b")→True`；"前缀是本层完整列名则禁止切分"的语义在 `choose` 内，见 §3.2-b。）
- **escape_quotes(string)**：`str` → `string.replace('"', '""')`（CSV 双引号转义）；非 str 原样返回。

### 2.3 `hone.utils` 契约
```python
class CSVUtils:
    def __init__(self, csv_filepath)      # 存 self.filepath；self._column_names=None；self._data_rows=None
    def _load(self)                       # 一次读完整个文件：rows=list(csv.reader(f))；_column_names=rows[0] if rows else []
                                          # _data_rows=[r for r in rows[1:] if r != []]；_loaded=True。'utf-8-sig'
    @contextlib.contextmanager
    def open_csv(self, mode="r", newline="")   # encoding="utf-8-sig"；"-"→yield sys.stdin（不关闭）；否则 open(filepath, mode, newline=newline, encoding=...)
    def get_column_names(self) -> list[str]    # 首次调用触发 _load()；返回 list(self._column_names) 副本
    def get_data_rows(self) -> list[list[str]] # 同上；返回逐行 copy（list(r)）后的列表副本

def parse_csv_file(csv_filepath) -> tuple[list[str], list[list[str]]]   # 内部用 CSVUtils（一次读取）
def output_json(json_struct, json_filepath) -> None
    # "-"→sys.stdout.write；否则 open(..., "w", encoding="utf-8", newline="\n")
    # 固定 json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=False)（或 dumps 后 write），末尾写一个 "\n"
def parse_json_file(json_filepath) -> object   # "-"→json.load(sys.stdin)；否则 utf-8 json.load
```
`hone/utils/test_utils.py`：`parse_json_file`（转导出）、`parse_csv_file`、`assert_json_equal(tc, actual, expected)`、`normalize(obj)`。**不放 unittest 用例。**
**硬约束**：CSV 解析只用 `csv.reader`（`newline=""`、`utf-8-sig`），禁止 `split(',')`/手工去引号；`"-"` 只能被消费一次（`_load` 保证）；`sys.stdin/stdout` 永不 close。

### 2.4 边界行为（`tests/test_boundaries.py` 逐条断言）
1. **空文件（0 字节）**：`cols=[]`、`rows=[]`、`convert()==[]`；CLI 输出 `[]\n`。
2. **仅表头无数据**：`convert()==[]`。
3. **无表头**：首物理行恒为表头，不报错（空文件见 1）。
4. **行短于表头**：缺失列对应键**在该行 dict 中省略**（不写 `null`、不写 `""`）。
5. **行长于表头**：多余单元格丢弃。
6. **重复表头**：后者覆盖前者（`idx` 字典语义），该键只出现一次。
7. **空字符串表头名**：按原样作为键 `""`（可作为叶子）。
8. **共享前缀**：`birth day/month/year` → 合并为嵌套对象。
9. **前缀是本层完整列名**：`a` 与 `a_b`、`adopted` 与 `adopted_since`、`reference` 与 `reference name` → 较长列保持**整名叶子**。
10. **schema 叶子映射的列在 CSV 不存在**：该键（在该行）**省略**，不抛异常、不写 null。
11. **CSV 有列但 schema 未引用**：丢弃。
12. **`"-"`**：`csv_filepath=="-"` 读 stdin，`json_filepath=="-"` 写 stdout；任意组合；同进程连续使用不坏。
13. **路径不存在**：库层 `FileNotFoundError`；CLI 捕获 → stderr 单行 `hone: error: <msg>` + 退出码 **1**。
14. **编码/换行**：CSV 读用 `utf-8-sig`（自动去 BOM，无 BOM 等价 utf-8）；输出 utf-8、`newline="\n"`、末尾一个 `\n`；CRLF 输入正常。
15. **多字符分隔符**：切分索引用 `i + len(d)`（不得假设单字符）；`-d "['::']"` 对 `x::y,x::z` 生成 `{"x":{"y":...,"z":...}}`。
16. **同层同前缀同余串冲突**（如 `a_b` 与 `a b` 归入同一 `p`）：后者覆盖前者（已知限制，不在样例中构造）。

### 2.5 CLI 契约
```
usage: hone [-h] [-d [DELIMITERS]] [-s [SCHEMA]] csv_filepath json_filepath
```
- `main(argv=None) -> int`；`python -m hone` 与 `hone` console script 行为一致（`hone = "hone.__main__:main"`）。
- `-d/--delimiters`：`nargs="?"`，`const=None`；`None` → `Hone.DEFAULT_DELIMITERS`；有值时**先 `ast.literal_eval`，失败再 `json.loads`**（不做"按逗号切"退化）；结果必须是**非空 list[str]**，否则 `parser.error(...)`（退出码 2）。
- `-s/--schema`：`nargs="?"`，`const=None`；有值时**仅 `json.loads` 字符串**（PRD 即"JSON object encoded as a string"；**无文件路径回退**）；结果必须是 dict，否则 `parser.error`（退出码 2）。
- 位置参数必填，`"-"` = stdin/stdout。退出码：**0** 成功 / **2** 参数错误 / **1** 运行期错误。
- **README 必须写明**：`-d`、`-s` 的可选值若紧跟，会被当作其值吞掉；请写成完整引号形式 `-d "['_']"`、`-s '{...}'`，否则 `csv_filepath` 会被吞并使 argparse 退出 2；无值而只想用默认值时**不要写** `-d`/`-s`。
- 调用顺序严格按 UML_sequence：`parse_args → Hone(delimiters) → convert(csv, schema) → output_json`。

---

## 3. 转换算法（A 照此实现；伪码可直接落地）

**3.1 语法候选（`get_valid_splits`）**：对 `r`、`d in self.delimiters`（顺序优先）、`r` 中每次出现位置 `i`：`p = r[:i]`，`rem = r[i+len(d):]`；`p.strip()` 与 `rem.strip()` 均非空才保留。返回 `[[p, rem], ...]`（分隔符顺序 → 出现位置）。

**3.2 本层选择（`choose(r, rel)`）**：
```python
def choose(self, r, rel):
    for d in self.delimiters:                     # 分隔符优先级
        start = 0
        while True:
            i = r.find(d, start)                  # 支持多字符分隔符
            if i <= 0:                            # 不存在或为空前缀
                if i < 0: break
                start = i + len(d); continue
            p, rem = r[:i], r[i+len(d):]
            start = i + len(d)
            if not p.strip() or not rem.strip(): continue
            if p in rel: continue                 # (b) 前缀是本层完整列名 → 禁止切分（example_b 的 a_b）
            if any(o != r and o.startswith(p + d) for o in rel):   # (a) 至少一个其它本层列名共享 "p+d"
                return (p, rem, d)
    return None
```
> 规则 (b) 是 `a_b`/`adopted_since`/`reference name` 保持叶子的原因；规则 (a) 使 `age (years)`、`weight (kg)`、`some 'quoted"' field"`（前缀唯一）保持整名列叶子，同时让 `birth day/month/year` 合并。**只切一刀**，`rem` 作为下一层相对名。

**3.3 建树（逐层相对名上下文，禁止全局表头）**
```python
def build(self, entries):        # entries: [(rel, orig), ...]；首层 rel==orig==原始列名
    rel = [r for r, _ in entries]; out = {}; groups = {}
    for r, orig in entries:
        sp = self.choose(r, rel)
        if sp is None:
            out[r] = orig                       # 叶子：键=本层相对名，值=完整原始列名
        else:
            groups.setdefault(sp[0], []).append((sp[1], orig))
    for p, child in groups.items():
        out[p] = self.build(child)
    return out
```
**不变量（测试断言）**：① 每个原始列名在树中作为某个叶子的值恰好出现一次；② 非叶子节点下 ≥2 个键（单例分组必退化为叶子）；③ 叶子键 = 该叶子在本层的相对名，叶子值 = 完整原始列名。
> 反例自检：`x_y` + `x_y_z` → 第 1 层 `rel={x_y,x_y_z}`：`x_y` 无分隔符→叶子；`x_y_z` 选 `p="x"` → 第 2 层 `rel={y, y_z}`：`y_z` 的 `p="y"` 因 `y in rel` 被 (b) 阻断 → 叶子。结果 `{"x": {"y": "x_y", "y_z": "x_y_z"}}`（正确，不会出现 leaf/dict 冲突）。

**3.4 数据填充**：见 §2.2 `populate_structure_with_data`（`idx` 反查、行短省略、缺列省略、每行 deepcopy）。

**3.5 schema 递归映射**：schema 为 dict → 逐键递归；为 str → 该键取该列名在本行的值（规则同 populate）。`nested_schema.json` 形如 `{"birth": {"year": "birth year", ...}, "name": "name"}` 直接生效，**不参与自动推断**。`get_schema` 即 `generate_full_structure`（叶子已存原始列名）。

**3.6 默认与覆盖**：`DEFAULT_DELIMITERS=[',','_',' ']`；`__init__(delimiters=...)` **完全覆盖**默认（不并集），保序。

**3.7 comma_test 反例审计（写入 docstring）**：`csv.reader` 解析出 2 列 `"test","ing"` 与 ` "beep"""`。前者内部逗号产生 `p='"test"'`，但同层无其它列以 `"test",` 开头 → 不共享 → 叶子；后者仅前导空格产生空前缀 → 丢弃 → 叶子。故输出 `[{" \"beep\"\"\"": "\"2", "\"test\",\"ing\"": "\"1"}]`，**无需为引号特判**。

**3.8 期望结果自检**：quotes_test → `birth` 嵌套 3 子键，`age (years)`/`weight (kg)`/`adopted_since`/`some 'quoted"' field"`/`adopted`/`name` 叶子；example_b → `a`、`a_b` 叶子，`b.c.{d,e}`、`b.d.{e,f}`，第 2 行 `b.d.f=="12"`；example_c → `birth` 嵌套 + `reference`/`reference name` 顶层叶子。
