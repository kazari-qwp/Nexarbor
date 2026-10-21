# 只读导航核验：中文语义检索、页面目录与章节展开、跨页链接

任务：task/5f94fd38271340899dce261391be1bee（mode=read）。全程只读，未修改任何记录。所有 method、score、section_id、行号均来自工具实际返回。

## 0. 方法与判定口径

- 语义检索：`kb_search(semantic=true)`，返回 `method` 字段。本次全部语义调用均返回 **hybrid**（向量+关键词融合），说明语义索引就绪并参与排序。
- 关键词回退：`kb_search(semantic=false)`，返回 **method=keyword**；同一中文查询在两集合均 **0 命中**，证明中文语义问题不能靠关键词兜底。
- Wiki 导航：`kb_fetch(view=outline)` 取目录 → `view=section&section_id=...` 展开章节 → `view=links` 查已解析关联 → 进入目标页并读取章节。Wiki 的 read 参数固定版本。

## 1. 查询一：「多台计算机共用数据库文件的限制」

### 1.1 RAG 集合 quake-source-docs（node instance-53334db5dad853ada65a-0）

`kb_search(semantic=true)` → method **hybrid**，total 3：

| 排名 | 记录 | 版本 | 命中章节 | score | 位置 |
| --- | --- | --- | --- | --- | --- |
| 1 | 555e87ece9cf4cbf8c91b3d2fc373f9f（0001） | 1 | L241「2. Situations Where A Client/Server RDBMS May Work Better」 | 0.599 | 第 251–293 行（章节 241–290） |
| 2 | f133872facee49068540e914b83be831（0002） | 1 | L10「1. Overview」 | 0.585 | 第 42–77 行（章节 10–81） |
| 3 | 56dea0631a56496f87bb107175c2d201（需求 v1 原文） | 1 | L1 | 0.582 | 第 1–20 行 |

沿 `section_fetch` 实际展开 0001 的 L241（`view=section, section_id=L241`），返回 241–290 行，关键原文：

- 「If there are many client programs sending SQL to the same database over a network, then use a client/server database engine instead of SQLite.」
- 「file locking logic is buggy in many network filesystem implementations (on both Unix and Windows)… two or more clients might try to modify the same part of the same database at the same time, resulting in corruption.」
- 「avoid using SQLite in situations where the same database will be accessed directly… and simultaneously from many computers over a network.」

### 1.2 Wiki 集合 quakedesk-wiki（node instance-78d9523725ec87628b4e-0）

`kb_search(semantic=true)` → method **hybrid**，total 5：

| 排名 | 页面 | 记录/版本 | 命中章节 | score |
| --- | --- | --- | --- | --- |
| 1 | 需求 v2（现行）与变更影响 | d2b160eab1314f1a8b04ccef97153ff6 / **1** | L40「3. 待评估提议（不是已验证结论）」 | 0.666 |
| 2 | 常见问题 | 296bf9f082f841849e9c311e00168f09 / **3** | L15「Q1」 | 0.642 |
| 3 | 项目知识总览 | 60cee721f0884a95b9ba474db7f6e077 / **2** | L19「现行条件（v2）」 | 0.642 |

### 1.3 关键词回退对照

- `kb_search(quake-source-docs, semantic=false, 同一中文查询)` → **total 0，method=keyword**。
- `kb_search(quakedesk-wiki, semantic=false, 「二进制JSON的版本条件」)` → **total 0，method=keyword**。

结论：中文语义查询依赖向量索引；关键词分支对这类问法无命中，不能把「0 命中」误当作库内没有资料。

### 1.4 实际导航路径 A（页面 → 目录 → 章节 → 跨页）

1. 语义命中 d2b160ea… v1，读其 `read` 参数所在页。
2. `kb_fetch(id=d2b160ea…, version=1, view=outline)`：9 个 section —— document、L11、L17（现行条件）、L30（版本升级影响）、L40（待评估提议）、L52（已落实变更）、L58（引用仍适用/需重核）、L69（修订约定）、L74（Related）。
3. `kb_fetch(view=section, section_id=L40)`：返回第 40–51 行；内容明确该提议「状态：待评估（proposal），未获项目确认，未做实测」，并引用 0001 第 2 节（记录 555e87ec… v1，241–290 行）与 0002 第 1 节（记录 f133872f… v1，10–81 行）。
4. `kb_fetch(id=d2b160ea…, view=links)`：6 条链接全部 `resolved`，含 **faq → 296bf9f082f841849e9c311e00168f09 v3**。
5. 沿该链接进入 FAQ：`kb_fetch(id=296bf9f0…, version=3, view=outline)` 得 17 个 section（Q1 L15 … Q13 L90、Q14 L98），再 `view=section, section_id=L90` 读取 Q13（第 90–97 行），内容为共享目录提议的状态与依据；该 section 的 `links` 字段回指 **requirements-v2（d2b160ea… v1，resolved）**，双向链接均可解析。

## 2. 查询二：「二进制JSON的版本条件」

### 2.1 RAG 集合

`kb_search(semantic=true)` → method **hybrid**，total 1（记录 3f96bb93535940a698476d077dadd85e，0005，版本 1），但三个 chunk 的首位并非 JSONB 定义：

| 排名 | 章节 | score | 位置 |
| --- | --- | --- | --- |
| 1 | L355「3.7. Performance Considerations」 | 0.675 | 382–413 行 |
| 2 | L1011「4.21. json_valid()」 | 0.667 | 1011–1059 行 |
| 3 | L283「3.6. JSON5 Extensions」 | 0.666 | 321–350 行 |

命中片段含 `json_group_array(jsonb(A))`、JSON BLOB 输入等，属于相关但非定义段。因此按目录二次定位：`kb_fetch(id=3f96bb93…, view=outline)` 显示「3.2. JSONB」为 L133（133–201 行，含子节 L153 3.2.1、L173 3.2.2），再 `view=section, section_id=L133` 展开，得到版本条件原文：

- 「Beginning with version 3.45.0 (2024-01-15), SQLite allows its internal "parse tree" representation of JSON to be stored on disk, as a BLOB, in a format that we call "JSONB".」
- 同节：JSONB 仅限 SQLite 内部使用（3.2.1），不应作为交换格式；`json_*` 返回文本，`jsonb_*` 返回二进制。

### 2.2 Wiki 集合

`kb_search(semantic=true)` → method **hybrid**，total 4：

| 排名 | 页面 | 记录/版本 | 命中章节 | score |
| --- | --- | --- | --- | --- |
| 1 | SQLite 版本边界（项目当前 3.46.0） | 9efc8dcf889d4bfe9a74bcba6758d279 / **3** | L54「4. 资料陷阱」 | 0.734 |
| 2 | 常见问题 | 296bf9f0… / **3** | L57「Q7. …JSONB 能用吗？」 | 0.679 |
| 3 | 项目知识总览 | 60cee721… / **2** | L19「现行条件（v2）」 | 0.676 |

### 2.3 实际导航路径 B（页面 → 目录 → 章节 → 跨页）

1. `kb_fetch(id=9efc8dcf…, version=3, view=outline)`：8 个 section —— L15（当前 3.46.0 可用）、L37（仍不可用）、L43（已失效的历史结论）、L54（资料陷阱）、L60（使用建议）、L66（Related）。
2. `kb_fetch(view=section, section_id=L43)`：第 43–53 行，表格明确「不能依赖 JSONB…→ 已失效：JSONB 与 jsonb_* 标量函数可用」，并注明 `jsonb_each/jsonb_tree`、`->` 负下标限制仍成立。
3. `kb_fetch(id=9efc8dcf…, view=links)`：4 条链接全部 `resolved`，含 **faq → 296bf9f0… v3**。
4. 进入 FAQ 并读 Q7：`kb_fetch(id=296bf9f0…, version=3, view=outline)` → `view=section, section_id=L57`（57–67 行），内容：当前版本可依赖 JSONB；3.45.0 起 JSONB，3.46.0 新增 `json_pretty()`；`jsonb_each/jsonb_tree`（3.51.0）与 `->` 负下标（3.47.0）仍不可用。

## 3. 由证据得到的事实结论

**多机共用数据库文件的限制**（0001 v1，第 241–290 行；0002 v1，第 10–81 行与 2.2 节）：
1. 多台计算机通过网络直接访问同一数据库应改用客户端/服务器引擎；
2. 网络文件系统锁实现常有缺陷，两客户端同时写同一区域可导致数据库损坏，SQLite 无法阻止；
3. WAL 要求同机共享内存，不能用于网络文件系统；同一时刻只允许一个写者。
4. 项目层面的表述为「待评估提议、未验证、不建议推进」（requirements-v2 L40；FAQ Q13 L90）。

**二进制 JSON 的版本条件**（0005 v1 第 133–201 行；0010/0011 发行说明）：
- JSONB 自 **3.45.0（2024-01-15）** 起提供，`jsonb_*` 与 JSON 生成函数输出二进制；项目现用 **3.46.0**，因此可用。
- `json_pretty()` 需 3.46.0（已满足）；`jsonb_each/jsonb_tree` 需 3.51.0、`->` 负下标需 3.47.0（均未满足）。

## 4. 语义检索 vs 关键词回退（本次实测）

| 查询 | 集合 | 调用语义 | 返回 method | total |
| --- | --- | --- | --- | --- |
| 多台计算机共用数据库文件的限制 | quake-source-docs | true | hybrid | 3 |
| 多台计算机共用数据库文件的限制 | quakedesk-wiki | true | hybrid | 5 |
| 多台计算机共用数据库文件的限制 | quake-source-docs | false | keyword | **0** |
| 二进制JSON的版本条件 | quake-source-docs | true | hybrid | 1 |
| 二进制JSON的版本条件 | quakedesk-wiki | true | hybrid | 4 |
| 二进制JSON的版本条件 | quakedesk-wiki | false | keyword | **0** |

索引状态：两次语义调用均正常返回 hybrid，未出现「索引未就绪/回退」提示，因此本次**没有**触发「缺索引」错误；关键词分支的 0 命中是检索方式差异，不是索引缺失。

## 5. 限制与未执行项

- RAG 语义对「二进制JSON」的首位命中是 3.7 性能节与 4.21 json_valid，不含 3.2 定义；本次通过目录（outline）二次定位到 L133，说明语义命中需配合章节导航，不能直接引用首位片段作为定义。
- 本次仅核验上述两个集合与两个问题，未评估 CSV/SQLite 集合的导航，也未做全文回归。
- 未修改任何知识记录；所有引用均固定记录版本（Wiki 页 v1/v2/v3，RAG v1）。
