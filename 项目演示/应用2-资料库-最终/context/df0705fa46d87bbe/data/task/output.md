# 归档收尾自查与导航抽查（含待办最终清零）

任务：task/0fb268bfc94a41eba5cbc827d1a31f50（mode=write）。本次做了两项工作：(A) 用 kb_intake 待办列表收尾，只补必要归档与来源关联，不新增重复资料；(B) 不指定集合做中文语义检索并实际沿 Wiki 入口导航。入库工具补充关联/排除入口后，待办已全部清零。

## A. 入库待办收尾

### A.1 收尾前待办（kb_intake 列表）

| intake | 内容 | 初始状态 |
| --- | --- | --- |
| 53b69a4db3ce43fe87b9cde8f4664296 | SOURCES.json | pending |
| b42d06fbb2024e02aea372ca1ea9c0c3 | 增量阶段任务说明（文本） | pending |
| 644e332280ad45a3b98b37099ab5febf | duplicate-document.md | pending |
| 08a75660445d4b26b3881c7c7253a0c6 | earthquakes-additional.csv | partial（剩 180 行） |
| 9b7e68fc5418438e88d394f1a7608704 | 本次收尾任务说明（文本） | pending |

### A.2 已完成的归档与来源关联（实际回执）

1. **补发资料 duplicate-document.md**（intake 644e3322）
   - `kb_store(collection=quake-source-docs, intake_id=644e3322…)` → 复用既有 0002 记录 **f133872facee49068540e914b83be831**，版本 1 → **2**；index 结果 `skipped 1`（无新增内容）。
   - 未新建文档记录，来源关联完成，待办关闭（`remaining_indices: []`）。

2. **追加观测 CSV**（intake 08a75660，此前只写入过第 1 行）
   - `kb_store(collection=earthquake-observations, intake_id=08a75660…)` → 剩余 180 行全部映射回既有记录，版本 2 → **3**；`remaining_indices: []`。
   - 观测总数保持 **481**（写入前后均为 481），未重复累计。

3. **SOURCES.json 原件关联**（intake 53b69a4d，工具新增入口后完成）
   - `kb_intake(action="associate", id=53b69a4d…, record_id=ca209cbdbc5c40a8bf2ef184d93416f1)` → **status: completed**。
   - 记录 **ca209cbd…** 版本仍为 **1**（正文与版本未变），其 `origins` 增加原件归档：`knowledge/intakes/53b69a4d…/original.json`，hash `14320e01…`。
   - 说明：此前 `kb_store` 因「RAG 只接受字符串」无法消费该 JSON 对象 intake；现以「关联已存 JSON 文本记录」的方式保留原件与来源，不再重复保存正文。

4. **任务指令类待办的排除**（不删除原件）
   - `kb_intake(action="dismiss", id=b42d06fb…, reason="内容为增量阶段任务指令文本，不是资料原件；已作为 task/767ab440… 的 input 保存，归档会产生重复与检索噪声。")` → **status: dismissed**。
   - `kb_intake(action="dismiss", id=9b7e68fc…, reason="内容为本次收尾自查任务指令文本，不是资料原件；已作为本任务的 input 保存，无需入库为知识资料。")` → **status: dismissed**。

5. **来源变化引起的页面指针刷新**（必要维护，只改 sources 版本指针）
   - 0002 记录升到 v2 后，引用它的 3 个页面被 lint 标为 stale，已按当前版本重新登记：
     - 需求 v2 页 d2b160eab1314f1a8b04ccef97153ff6：v1 → **v2**
     - 资料与来源页 2fa441087fe94d909939f8c93c8d282e：v2 → **v3**
     - FAQ 296bf9f082f841849e9c311e00168f09：v3 → **v4**
   - 正文未改动，只同步 sources 指针与「补发资料已完成来源关联」的说明；`needs_refresh` 已变为 false。
   - `kb_wiki lint` 复核：7 页、36 条边，orphans / stale / unsourced / wantedPages 均为空。

### A.3 待办清零核对

`kb_intake`（不填 id）最新结果：**items 为空，total 0**。5 条待办全部以「存储 / 关联 / 排除」三种方式关闭，无遗留原件。

## B. 不指定集合的中文语义检索与 Wiki 导航

### B.1 检索

`kb_search(semantic=true, query="为什么不能把数据库放在两台机器共享的目录上")`，未指定集合 → **method=hybrid，total=14**，前五条：

| 排名 | 入口 | 类型 | 版本 | 命中位置 |
| --- | --- | --- | --- | --- |
| 1 | 296bf9f082f841849e9c311e00168f09 | wiki（FAQ） | **4** | L86（Q12）/ L82 / L15；snippet 含 Q13 全文 |
| 2 | 56dea0631a56496f87bb107175c2d201 | rag（需求 v1） | 1 | L1 第 1–20 行 |
| 3 | 555e87ece9cf4cbf8c91b3d2fc373f9f | rag（0001） | 1 | L241「Client/Server RDBMS」251–293 行 |
| 4 | d2b160eab1314f1a8b04ccef97153ff6 | wiki（需求 v2） | **2** | L40「待评估提议」 |
| 5 | 60cee721f0884a95b9ba474db7f6e077 | wiki（总览） | **2** | L19「现行条件」 |

说明：同一查询同时命中 Wiki 与 RAG，说明未指定集合时两类索引都参与。

### B.2 沿 Wiki 入口实际导航

1. 取第一条 Wiki 入口 FAQ（296bf9f0… **v4**），`view=outline` 得到 17 个 section（Q1 L15 … Q13 L90、Q14 L98、Related L102）。
2. `view=section, section_id=L90` 展开 **Q13**（第 90–97 行）：状态为「待评估、未验证、项目未确认」，引用 0001 第 2 节与 0002 第 1 节，结论为「不建议推进」。
3. 该 section 返回 `links`：**requirements-v2 → d2b160eab1314f1a8b04ccef97153ff6，status=resolved，version=2**。
4. 沿该已解析链接进入目标页，`view=section, section_id=L40` 读取「3. 待评估提议」（第 40–51 行）：与 FAQ Q13 一致，并给出 0001（555e87ec… v1，241–290 行）与 0002（f133872f… **v2**，10–81 行；注明 v2 为重复资料关联后的版本、正文未变）的具体位置。

结论简述：共享目录访问同一 SQLite 文件仍属**待评估提议**，官方文档不支持（网络文件系统锁缺陷可致损坏；WAL 需同机共享内存），建议不作为方案推进；Wiki 与 RAG 引用链一致，页面链接与章节参数可用。

## C. 收尾后状态

| 项目 | 状态 |
| --- | --- |
| 入库待办 | **0**（5 条全部关闭：2 存储、1 关联、2 排除） |
| 观测集合 | **481** 行（未因重复提交增长） |
| RAG | 16 条（0002 因重复资料关联升 v2，正文未变；SOURCES.json 仍 v1 并新增原件 origins） |
| Wiki | 7 页，lint 无 stale/orphan/unsourced；requirements-v2 v2、requirements-v1 v2、overview v2、sqlite-version v3、observations-guide v2、sources-and-collections v3、faq v4 |

## D. 仍存在的限制

1. **对象型 JSON 不能直接作为 RAG 文档正文**：SOURCES.json 只能以「JSON 文本记录 + 原件关联」的方式保留；正文与 intake 原件分属记录与 origins，检索时命中的是文本记录。若需原文级召回，需另行提供文本版。
2. **本机 SQLite 实际版本仍未核实**：3.46.0 是项目声明值，未做 `sqlite_version()` 探测。
3. **共享目录提议仍待项目决策**：知识库只给出文档评估意见，未做并发/锁语义实测。
4. **WAL-reset bug 未纳入知识页**：0002 第 11 节显示受影响区间 3.7.0–3.51.2，回移仅列 3.44.6、3.50.7；项目 3.46.0 的补丁决策仍待确认。
5. **0113/0013 字段定义缺失、导出缓存实现细节缺失、负责人与上线日期未指定**：均属资料本身的空白，未在本次收尾中臆测补齐。
6. 重复提交与关联操作会产生版本号递增（0002→v2、181 条观测→v3 等），这是「不新增记录」策略的可见痕迹，不代表内容变化。

## E. 引用登记

- 原件关联：SOURCES.json 记录 ca209cbdbc5c40a8bf2ef184d93416f1，版本 1；origins 指向 intakes/53b69a4db3ce43fe87b9cde8f4664296/original.json（hash 14320e01…）。
- 补发资料：0002 记录 f133872facee49068540e914b83be831，版本 2。
- 观测去重：记录 2e8dda69e18f472bbd6d1f5cf31291eb，版本 3；集合 485b34c69ca84e0fb2174ba6375d3a12 计数 481。
- 页面：FAQ 296bf9f0… v4（L90）；需求 v2 d2b160ea… v2（L40）；资料与来源 2fa44108… v3；版本页 9efc8dcf… v3。
- RAG：0001 555e87ec… v1（L241）；0002 f133872f… v2（第 1 节）。
