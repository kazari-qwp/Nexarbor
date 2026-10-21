## 第1轮 · admin-1b6b2bf35b0c4235a35a43fbc6e91321
【Leader 第1轮：建议按以下内容定稿，Recorder 可直接吸收进输出板】

## 0. 本轮关键决策（先冻结，后并行）
- 算法采用「共享前缀分组递归」，而不是"遇到分隔符就切"。这是唯一能同时解释 example_b（a_b 为叶子）与 quotes_test（"some 'quoted\"' field\"" 为叶子）的规则。
- 公共契约以本发言第2节为准，A 在阶段0 落地为 hone/hone.py 的骨架+docstring，B/C/D 只按契约编码，不擅自改签名。
- 文件所有权严格切分，4 人零共享文件；D 独占 tests/ 与根 README.md，其他人只提 issue/补丁建议，由 D 落盘。
- 测试一律以 CSV 为真值、不修改 workspace/task；examples/README.md 中 example_b 第2行 b_d_f 写成 "1" 属文档笔误，真值为 "12"，断言必须用 "12"。

## 1. 目标与验收清单（逐条可验证）
1. `python -c "import hone; print(hone.Hone)"` 成功；`hone.hone.Hone` 可导入。
2. `Hone().convert(path)` 对 data_file 三组 dataset.csv 输出分别等于各自 nested_dataset.json（含 comma_test 的怪引号表头）。
3. `Hone().convert(small_cats/dataset.csv, schema=json.load(nested_schema.json))` 结果与自动推断一致，且等于 nested_dataset.json。
4. example_a/c 输出与 examples/README 展示一致；example_b 输出为 a/a_b 叶子 + b.c.d、b.c.e、b.d.e、b.d_f 嵌套（b_d_f 第二行为 "12"）。
5. `python -m hone -h` 退出码 0，usage 行与 README 一致（`hone [-h] [-d [DELIMITERS]] [-s [SCHEMA]] csv_filepath json_filepath`）。
6. `python -m hone in.csv out.json` 写文件成功；`python -m hone - -` 从 stdin 读、向 stdout 写；输出恒为 `json.dumps(obj, indent=2, sort_keys=True) + "\n"`。
7. `python -m hone -d "['-']" in.csv -` 能覆盖默认分隔符并正确嵌套（自造用例）。
8. 边界用例全部按第2节定义通过：空文件、仅表头、行短/行长、重复列名、schema 引用缺失列、相对/绝对路径、UTF-8。
9. `python -m unittest discover -s tests -v` 全绿；`python -m unittest`（根目录）亦可发现并全绿。
10. `python -m pip install -e .`（或 wheel 安装）后，在仓库外可 `python -c "import hone"` 且 `hone --help`/`python -m hone` 可用；pyproject 元数据完整。
11. `python examples/demo.py`、`bash examples/demo.sh` 可直接运行并打印合法 JSON。
12. 仓库根 README.md 含安装、CLI 文件输出、CLI 标准输出（"-"）、Python 模块调用四段可复制示例；LICENSE 为 MIT。

## 2. 文件/模块布局与公共接口契约
布局（与 architecture_design.md 一致，不多建顶层模块）：
```
hone/__init__.py          A  from .hone import Hone；__all__=["Hone"]；__version__="1.0.0"
hone/hone.py              A  Hone 全部方法
hone/__main__.py          C  main() + SystemExit(main())
hone/utils/__init__.py    B  导出 CSVUtils/parse_csv_file/output_json/parse_json_file
hone/utils/csv_utils.py   B
hone/utils/json_utils.py  B
hone/utils/test_utils.py  B
pyproject.toml            C
LICENSE                   C
examples/demo.py|demo.sh  C（保持可运行，不改样例 CSV）
README.md                 D
tests/                    D（__init__.py + test_*.py）
```
核心依赖约束：hone.py 与 hone/utils/*.py 只 import 标准库 csv/json/os/sys/contextlib/io；CLI 额外可用 argparse 与 ast（用于解析 `-d` 的 Python 字面量列表，属标准库；若评审要求更严，可只支持 json.loads）。

### Hone 契约
```python
DEFAULT_DELIMITERS = [',', '_', ' ']   # 类属性，实例 self.delimiters 复制一份
class Hone:
    def __init__(self, delimiters=None): ...        # None→DEFAULT_DELIMITERS；传 list 则原样使用（校验为非空 str 列表，否则 ValueError）
    def set_csv_filepath(self, csv_filepath): ...   # 记录路径并重置 csv 缓存；"-" 合法
    def convert(self, csv_filepath, schema=None): ...  # → list[dict]，行序=CSV 数据行序
    def get_schema(self, csv_filepath): ...            # → dict；叶子值为原始列名（可含分隔符）
    def generate_full_structure(self, column_names): ...      # → dict；叶子值为原始列名
    def populate_structure_with_data(self, structure, column_names, data_rows): ...  # → list[dict]
    def get_nested_structure(self, parent_structure): ...     # → dict（深拷贝归一化，不改变键/叶子）
    def get_leaves(self, structure, path=(), result=None): ...  # → list[tuple[tuple[str,...], str]]，(路径元组, 叶子字符串)
    def get_valid_splits(self, column_name): ...      # → list[list[str]]：所有候选切分（按分隔符优先级、去空白、去空 token、长度≥2）
    def get_split_suffix(self, split, column_name): ...  # → str：column_name 去掉 split[0]+其分隔符后的余串，供递归
    def clean_split(self, split): ...                 # → list[str]：strip 每段并丢弃空段
    def is_valid_prefix(self, prefix, base): ...      # → bool：prefix 是"嵌套前缀"（在当前列名集合中被≥2列共享，且 prefix 本身不是完整列名）；base 为当前列名，用于排除自身
    def escape_quotes(self, string): ...              # → str：把 " 转成 \"（JSON 风格），不做其它改动
```
- convert：`set_csv_filepath` → CSVUtils 取 column_names/data_rows → schema is None 时 `schema = get_schema(csv_filepath)`（复用已读缓存，避免二次读文件也可，语义一致即可）→ `populate_structure_with_data(schema, cols, rows)`。
- populate 递归：dict→递归；str 叶子→`column_names.index(leaf)` 取该行值；schema 叶子对应的列不存在时填 `None`（不抛异常）；schema 未覆盖的 CSV 列被忽略。
- 表头空串按原样作键；重复列名后者覆盖前者（dict 语义，文档写明）。

### utils 契约
```python
class CSVUtils:
    def __init__(self, csv_filepath): ...            # 保存 filepath；csv_filepath=="-" 表示 stdin
    @contextlib.contextmanager
    def open_csv(self, mode='r', newline=''): ...    # yield 文本句柄；encoding='utf-8'；"-" 读用 sys.stdin；不关闭 stdin
    def get_column_names(self): ...                  # → list[str]，首行；空文件→[]
    def get_data_rows(self): ...                     # → list[list[str]]，其余行，原样保留；空/仅表头→[]
def parse_csv_file(csv_filepath): ...                # → (column_names, data_rows)，组合上述
def output_json(json_struct, json_filepath): ...     # 文件：json.dump(indent=2, sort_keys=True)+换行；"-"：写 sys.stdout
def parse_json_file(json_filepath): ...              # → dict/list；"-" 读 stdin
```
行短于表头时缺列取 ""；行长于表头时多余单元忽略（在 populate 内实现，文档写明）。

### CLI 契约
```
hone [-h] [-d [DELIMITERS]] [-s [SCHEMA]] csv_filepath json_filepath
-d/--delimiters  nargs='?', const=DEFAULT（即只写 -d 时沿用默认）；值按 json.loads 解析，失败回退 ast.literal_eval；结果须为非空字符串 list，否则 parser.error（退出码2）
-s/--schema      nargs='?', const=None；值按 json.loads 解析为 dict
csv_filepath/json_filepath  位置参数，必填，"-" 表示 stdin/stdout
```
main()：解析 → `Hone(args.delimiters)` → `schema = json.loads(args.schema)`（有值时）→ `convert` → `output_json` → 返回 0；异常转 `parser.error` 或打印 stderr 并返回非0（测试只断言成功路径与 help）。

## 3. 转换算法说明（A 照此实现）
标记：names=当前子树下的原始列名列表（含已被判定为叶子的）。
1. 对每个 name 选**候选切分**：按 self.delimiters 顺序，找第一个"出现在 name 中且 clean_split 后段数≥2"的分隔符，split 后 clean，得到 parts；无则叶子。
2. 统计本子树所有候选 parts[0] 的出现次数（一个 name 只贡献一次）。
3. 对每个 name：若 parts 存在 且 count(parts[0])≥2 且 parts[0] 不等于本子树任一原始列名（即 parts[0] not in names）→ 归入分组 parts[0]，子问题名 = 去掉前缀后的余串（即 get_split_suffix）；否则 `result[name] = name`（叶子，保留完整原名，包括带分隔符的名字）。
4. 对每个分组递归执行 1-3，结果挂到 `result[parts[0]]`。
5. 叶子→数据：见 populate。
关键性质（必须写进 docstring）：
- 共享前缀才嵌套：birth day/month/year→birth.{day,month,year}；age (years) 的 "age" 只出现一次→整列叶子。
- 完整列名可"截断切分"：存在列 a 时，a_b 的前缀 "a" 是完整列名→a_b 保持叶子；同理 adopted 与 adopted_since、reference 与 "reference name"。
- example_b：a、a_b → 叶子；b_c_d/b_c_e/b_d_e/b_d_f 共享 b→b 下 c、d 分组→c.{d,e}、d.{e,f}；第二行期望值 b_d_f="12"。
- 分隔符优先级 DEFAULT=[',','_',' ']；混用分隔符靠递归自然处理（如 "b c_d" 先按 _ 切，再对余串按空格继续）。
- schema 递归映射：schema 为 dict→逐键递归；为 str→该键取该列名对应值；示例 nested_schema.json 中 birth:{year:"birth year",...} 直接生效，不参与自动推断。
- 边界：空文件→[]；仅表头→[]；无表头无法识别，首行恒为表头；列名/值均按 csv 模块默认解析（comma_test 的 `"""test"",""ing"""` 由 csv.reader 解析为 `"test","ing"`，不得手工 strip 引号）。

## 4. 四个任务包（文件所有权互斥）
阶段0（A，先做，30分钟）：用组内 git.workspace 建主仓+4 个 worktree（`.worktrees/a-core` 等，分支 feat/a-core…），把 hone/__init__.py、hone/hone.py（全部方法骨架+上述 docstring+NotImplementedError）、hone/utils/__init__.py 空壳、目录结构提交到 integration 分支；贴出契约清单。
- A 包｜核心算法：hone/__init__.py、hone/hone.py。实现第2、3节全部 Hone 方法。独立自测：`python -c "from hone.hone import Hone; print(Hone().get_valid_splits('birth day'))"` 及临时脚本覆盖 example_a/b/c（不依赖 tests/）。
- B 包｜utils 与 schema 校验：hone/utils/{__init__,csv_utils,json_utils,test_utils}.py。实现第2节 utils 契约；test_utils 提供 load_json/assert_json_equal/读取 data_file 夹具的 helper（不写 unittest 用例）。独立自测：`python -c "from hone.utils import CSVUtils; print(CSVUtils('data_file/quotes_test/dataset.csv').get_column_names())"`；并独立用脚本核对 small_cats schema 映射结论，发现 hone.py 缺陷提 issue 给 A，不直接改 A 的文件。
- C 包｜CLI+打包+demo：hone/__main__.py、pyproject.toml、LICENSE、examples/demo.py、examples/demo.sh。按 CLI 契约实现；demo.py 用 `from hone.hone import Hone` 打印 indent=2。独立自测：`python -m hone -h`、`python -m hone data_file/small_cats_dataset/dataset.csv /tmp/o.json`、`python examples/demo.py`。pyproject：name="hone"、version="1.0.0"、requires-python=">=3.8"、dependencies=[]、[project.scripts] hone="hone.__main__:main"、setuptools 后端、include hone*。
- D 包｜测试+回归+README：tests/、README.md。先按第5节写用例（可在 A/B 未完成时写、用 import 契约），再跑全量回归；README 四段示例+开发/测试命令。独立自测：`python -m unittest discover -s tests -v`。
依赖与合并顺序：阶段0(A) → A、B 并行 → 先合 A、立即合 B（文件不相交，import 路径已冻结）→ 合 C → 合 D 跑全量；每次合并后 integration 分支必须能 `python -m unittest discover -s tests`（D 合入前由合并者跑 D 分支用例）并跑三条 CLI 冒烟。冲突处理：任何跨所有权修改先开 issue，由文件所有者改；合并者不代写实现。

## 5. 测试计划（D 实现，具体断言）
- test_csv_utils：三组 dataset 的 column_names 数量（comma 2 列、quotes 9 列、small 8 列）；comma 表头解析值 `'"test","ing"'` 与 `' "beep"""'`；data_rows 行数（1/4/4）；空文件与仅表头→([],[])。
- test_hone_core（三组 golden）：对 data_file/{comma,quotes,small_cats}_test/dataset.csv，`Hone().convert(...) == json.load(nested_dataset.json)`（断言用 == 结构比较，不比较缩进）。
- test_schema：small_cats `convert(dataset, schema=load(nested_schema.json)) == load(nested_dataset.json)`；自造 schema `{"m":"missing"}`→`[{"m":None}]`；schema 少一列时输出不含该列。
- test_examples：example_a 输出逐字段断言（Tommy/Clara/... 的 birth 嵌套与 adopted_since 叶子）；example_c 断言 reference 与 "reference name" 均为顶层叶子；example_b 断言精确结构，第二行 b.d.f=="12"，且 "a_b" in row。
- test_algorithm：get_valid_splits("birth day") 含 ["birth","day"]；is_valid_prefix("birth","birth day") True、is_valid_prefix("a","a_b") False；escape_quotes('a"b')=='a\\"b'；重复列名覆盖、行短补 ""、行长忽略。
- test_cli（subprocess，sys.executable -m hone，cwd=仓库根，临时目录输出）：①文件→文件，读回==nested_dataset；②`-`→`-` 用 input=dataset 文本，stdout 必须精确等于 `json.dumps(expected, indent=2, sort_keys=True)+"\n"`；③`-s "<nested_schema json>" - -` 与②同结果；④`-d "['-']"` 自造 `x-y,x-z` 两行→`x.y/x.z` 顶层；⑤`-h` 返回0且含 usage；⑥输入不存在的路径→非0。
- test_packaging_demo：demo.py 子进程返回0且 stdout 可 json.loads；pyproject 可被 tomllib 解析（若 Python<3.11 则跳过）。
- 运行命令：`python -m unittest discover -s tests -v` 与仓库根 `python -m unittest`（tests/__init__.py 保证可发现）；测试中只读 workspace/task，写操作全用 tempfile。

## 6. 发布清单
1. pyproject 元数据齐全（name/version/description/readme/license/requires-python/classifiers/scripts），无第三方依赖，版本 1.0.0。
2. 构建与自测：`python -m pip install -e .`；`python -m unittest discover -s tests -v`；`python -m hone -h`；三组样例+examples 全绿。
3. 候选整合：integration 分支按 A→B→C→D 合并，打 `v1.0.0-rc1`。
4. 全员交叉验收（每人跑不同侧重点并回复通过/问题）：A 跑 CLI stdin/stdout；B 跑 schema+utils；C 跑安装后仓库外导入与 demo；D 跑全量 unittest 与样例 diff。
5. 可选 dist：`python -m build`（无 build 则 `python -m pip wheel . -w dist`），产物不入库；打 tag `v1.0.0`，输出验收报告到仓库 RELEASE_NOTES.md（D 负责）。

## 7. 风险与修复策略
- example_b README 笔误（"1" vs "12"）：以 CSV 数据为准，测试写 "12"，README 沿用输入输出但注明真值。
- 引号/逗号表头解析错：统一走 csv.reader，禁止自写 split；comma_test golden 必测。
- 用"共享前缀"规则误判（如 "age (years)" 被嵌套）：单例前缀一律叶子，测试覆盖。
- 混用分隔符歧义：固定"按 delimiters 顺序取第一个可切分隔符"，文档写明；测试覆盖一种混用。
- 并行冲突：文件所有权+阶段0 骨架+issue 机制；合并由固定一人（建议 A）执行，冲突退回所有者。
- stdin 不可 seek/重复读：convert 内只读一次；CLI 直接用路径透传。
- 平台差异：统一 encoding='utf-8'、newline=''；输出显式 "\n"；测试用 pathlib 与 sys.executable。
- 权限/路径：测试不写 workspace/task，输出用 tempfile；样例文件只读。
Recorder 请把以上并入输出板，第2轮我只补充/纠偏。

## 第1轮 · admin-b17b2b1dc2de47d9b69bd36da32f2b0f
【成员1 第1轮建议稿：可直接并入输出板的实施计划要点】

一、关键契约判定（请Recorder优先固化，执行成员看不到讨论，必须写进计划）
1) 转换一律用标准库 csv.reader（newline=''，utf-8）逐行解析，禁止 split(',')；comma_test 与 quotes_test 的期望 JSON 只有在 csv 引号规则下才能复现（如 comma_test 得到 2 个列名：`"test","ing"` 与 ` "beep"""`，值 `"1`/`"2`）。
2) 类型不做推断：所有叶子值均为 str；JSON 输出 indent=2、sort_keys=True；文件与 stdout 末尾统一写一个 "\n"。
3) 空文件/仅表头：get_column_names()=[]、get_data_rows()=[]、convert()=[]，CLI 输出 "[]"；无表头（空文件）不报错。空行（csv 返回 []）跳过。
4) 行字段少于表头→缺列补 ""；多于表头→忽略多余；表头重复→后者覆盖前者。
5) schema 叶子列名不存在于 CSV→该叶子输出 ""（保持结构）；CSV 有而 schema 未引用→丢弃。schema 既接受 dict 也接受 JSON 字符串（convert 内部 json.loads）。
6) "-"：csv_filepath 为 "-" 读 sys.stdin；json_filepath 为 "-" 写 sys.stdout；两者可任意组合；不关闭 sys.stdin/stdout。
7) 分隔符 split 规则（核心，必须逐字写进 CONTRACT.md）：
   - 候选切分：对列名 r，按 self.delimiters 顺序取每个分隔符的每次出现，切成 (prefix, suffix)，均非空。
   - 有效切分：a. prefix 不等于同层任一列名（防止 leaf/dict 冲突，example_b 的 a_b、adopted_since 因此保留）；b. 同层至少还有另一个列名以 prefix+该分隔符 开头（真正需要合并，weight (kg)/age (years)/quoted 字段因此不切）。两层都满足才有效。
   - 选择最短 prefix（并列时按 delimiters 顺序、再按出现位置）作为第一层；按 prefix 分组，对组内 suffix 递归执行同样规则；无有效切分则该键映射“原始列名”作叶子。
   - 这保证：birth day/month/year→birth.{day,month,year}；b_c_d…→b.c.d/e、b.d.e/f；example_b 得到 a、a_b 平铺；所有原始列名在 schema 中恰好出现一次。
8) 公共返回结构：convert→list[dict]（行序保持）；get_schema/generate_full_structure→嵌套 dict，叶子值=原始表头字符串；get_leaves(structure, path=None, result=None)→[(path_tuple, 原始列名)]。
9) 方法签名建议：Hone.__init__(delimiters=None, csv_filepath=None)，None→复制 DEFAULT_DELIMITERS=[',','_',' ']；convert(csv_filepath=None, schema=None)（None 时用 set_csv_filepath 已设值，未设则报 ValueError）；其余按任务文本。CSVUtils.open_csv(mode='r', newline='') 用 @contextmanager；output_json(json_struct, json_filepath) 支持 "-"。
10) example_b.json/README 末行把 12 写成 "1" 的迹象：D 包回归以 CSV 真值为准，只在该单元格记 known upstream typo，绝不修改样例。

二、包布局（A 首提交即建全目录与 CONTRACT.md，其他人只改自己文件）
pyproject.toml、LICENSE、README.md、hone/{__init__.py,__main__.py,hone.py,utils/{__init__.py,csv_utils.py,json_utils.py,test_utils.py}}、hone/test/（或 tests/，建议 hone/test/ 与 architecture 对齐，__init__.py 必备）、scripts/{check_a,check_b,check_c,check_d,acceptance}.py、examples 与 data_file 只做只读拷贝（记录 sha256，不修改原件）。

三、四人任务包（无 Leader，文件所有权隔离，合并顺序 A→B→C→D）
A 包（核心算法）：hone/hone.py、hone/__init__.py、CONTRACT.md、scripts/check_a.py。范围：generate_full_structure/get_nested_structure/get_leaves/get_valid_splits/get_split_suffix/clean_split/is_valid_prefix/populate_structure_with_data/convert/get_schema/set_csv_filepath/escape_quotes。依赖仅约定接口的 utils 桩。自测：python scripts/check_a.py 断言 example_a/b/c 的 schema 与逐行数据。
B 包（IO/工具）：hone/utils/*、scripts/check_b.py。CSVUtils 三方法、output_json/parse_json_file、test_utils（load_json/normalize/assert helpers）。自测：python scripts/check_b.py（读 data_file 三组、"-" 读写、空文件、Schema JSON 解析）。
C 包（CLI/打包/demo）：hone/__main__.py、pyproject.toml、examples/demo.py（如需）、scripts/check_c.py。argparse 用法严格 `hone [-h] [-d [DELIMITERS]] [-s [SCHEMA]] csv_filepath json_filepath`；-d 用 ast.literal_eval 校验 list[str]，-s 用 json.loads；错误走 parser.error→退出码2；main(argv=None)->int。自测：python -m hone --help；python -m hone examples/example_a.csv -；stdin/文件输出。
D 包（测试/回归/README/验收）：hone/test/*、README.md、scripts/check_d.py、scripts/acceptance.py、ACCEPTANCE.md。测试先按契约写，不等实现；覆盖第5节全部用例。D 兼任发布验证者（无否决权，失败按文件所有权退回对应成员）。

合并门禁：每包 merge 到 integration 前必须 `python -m compileall hone` 且 `python scripts/check_<X>.py` 绿；冲突只允许在 CONTRACT.md 评审后由对应 owner 解决。

四、测试计划（D 落地，均用标准库 unittest）
- data_file/comma_test/dataset.csv → 与 nested_dataset.json json.loads 后完全相等；断言列名/值含引号字符。
- quotes_test → 同法完全相等（含 some 'quoted"' field" 与内嵌双引号）。
- small_cats_dataset/dataset.csv → 自动转换 == nested_dataset.json；convert(..., schema=nested_schema.json) == 同上；get_schema == nested_schema.json（语义相等）。
- examples/a,b,c → 与 *.json 语义相等；example_b 逐值对照 CSV，已知 typo 单点豁免。
- CLI：文件输出（tmpdir，比较语义+`json.dumps(...,indent=2,sort_keys=True)+"\n"` 文本）；"-" stdout；stdin 管道；-d 自定义（example_b 用 ['_']）；-s（small_cats schema）；非法 -d/-s 退出码2；空文件 "[]"。
- 方法级：get_valid_splits/is_valid_prefix/clean_split/get_leaves/escape_quotes 边界；无表头、缺列 schema、重复表头。
- 门禁命令：`python -m unittest discover -s hone/test -t . -v`、`python scripts/acceptance.py`。

五、发布清单
pyproject：name="hone"、version="0.1.0"、requires-python>=3.8、license MIT、dependencies=[]、[project.scripts] hone="hone.__main__:main"、setuptools packages.find include=["hone*"]；版本同时写入 hone/__init__.py 并由测试校验一致。构建：`python -m pip wheel . -w dist`（有 build 则 `python -m build`）；干净 venv 中 `pip install dist/*.whl` 后跑 `hone --help`、示例转换、`python -m unittest`。流程：integration 全绿→打 v0.1.0-rc1→4 人各自在全新 worktree 跑 acceptance 并在 ACCEPTANCE.md 签名→合并 main、打 v0.1.0、产出 dist、发布说明（README 安装/CLI 文件输出与 "-" 输出/Python 调用/demo）。

六、风险与修复
引号解析（最高）：只用 csv 模块并用三组 data_file 做金标准；example_b 期望文件疑似 typo：以 CSV 为准并记录；切分规则歧义：CONTRACT.md 固化上述两条有效切分条件与示例，隐藏用例以“每个原始列名恰好一个叶子”为不变量；leaf/dict 冲突：同层列名阻断切分；schema 缺列：固定为 ""，不得 KeyError；CRLF：csv newline=''、输出统一 "\n"、utf-8；argparse 可选值歧义（-d/-s 后接位置参数）：文档要求带引号，测试覆盖并 parser.error；并行冲突：目录/文件所有权+固定合并顺序+CONTRACT 冻结；时间风险：D 的测试先于实现，B 的 utils 桩先合入让 A/C 可编译。第2轮请重点确认：切分规则表述、schema 缺列语义、example_b typo 处理、D 是否兼任验收人。

## 第1轮 · admin-86d82ae747274e62929c77eb2a550551
R1 提交（Recorder）：输出板已写成可执行草案（7 节全）。核心裁定摘要，请各位下轮集中核对/纠错：

1) 算法关键判定（决定 data_file 三组能否逐字复现）：一个列名在某分隔符处可切分，当且仅当 (a) 切出的前缀不是完整列名（→ example_b 的 "a_b" 因存在 "a" 列而保留为叶子）；(b) 该前缀至少被另一个列名共享（base==prefix 或 base.startswith(prefix+d)）→ 所以 "birth day/month/year" 合并为 birth；而 "age (years)"、"weight (kg)"、"some 'quoted\"' field\"" 的前缀无人共享，整名列作叶子。多候选切分按 delimiters 顺序优先、再按位置从左到右。
2) 已知样例笔误：examples/example_b.json 第 2 行 b.d.f 期望写成 "1"，正确应为 "12"（样例只读，测试内修正期望并在注释引用）。
3) 切分/契约：Hone 12 个方法签名与语义、utils（CSVUtils/output_json/parse_json_file/parse_csv_file、"-" 用 contextlib 不关闭标准流）、CLI 退出码 0/1/2、schema 缺键省略、行列不齐按 zip 语义——均已在板上写死。
4) 4 包所有权与合并顺序：B(utils 地基)→A(核心算法)→C(CLI/打包/demo)→D(黄金测试/README/tests/__init__)，文件所有权不交叉；各包自带 tests/test_* 独立文件避免冲突。
5) 发布：pyproject name=hone version=1.0.0、console script hone=hone.__main__:main、无依赖；验收命令为 unittest discover + wheel + venv。

请重点挑刺：(i) §3.2 切分规则是否有反例（尤其 comma_test 的 `"test","ing"` 与 ` "beep"""` 两个怪列名）；(ii) helper 方法（get_leaves/get_split_suffix/get_nested_structure）语义是否够实现；(iii) 4 包切分是否真能不冲突；(iv) 测试断言是否漏项。下轮我据反馈定稿并保存最终成果。
