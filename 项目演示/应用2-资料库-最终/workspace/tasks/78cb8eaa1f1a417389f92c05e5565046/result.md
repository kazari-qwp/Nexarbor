# 只读复查交付：当前知识库状态、版本依据与待核对项

任务：task/78cb8eaa1f1a417389f92c05e5565046（mode=read）。本次未修改任何知识记录；所有结论来自实际读取，未凭记忆补写。无法核查的内容在文末单列。

## 1. 观测数据现状与重复检查

集合 `earthquake-observations`（485b34c69ca84e0fb2174ba6375d3a12 / instance-db4021b056f586415d9e-0）实际查询结果：

- 总数：**481**
- network：**us 477、ak 2、ci 1、tx 1**
- 最大震级：**6.5**，event_id **us7000ne51**（2024-09-15T22:22:48.018Z，mww，network us，唯一一条）

重复记录核查（三项证据）：

1. 数量核算：初始快照 300 + 追加 181 = 481，等于当前计数，未多出记录。
2. 单条抽查：`kb_search(earthquake-observations,"us6000nsv4")` → total **1**，记录 2e8dda69e18f472bbd6d1f5cf31291eb，version 3。
3. 补发技术资料：`kb_search(quake-source-docs,"Write-Ahead Logging")` → total **2**，仅 SOURCES.json 记录 ca209cbdbc5c40a8bf2ef184d93416f1 与 0002 记录 f133872facee49068540e914b83be831；补发的 duplicate-document.md（sha256 56689d1a…）没有形成第三条副本。

结论：补发资料未造成文档重复，重复提交未造成观测重复；重复提交只让 181 条记录的版本号递增（内容未变）。

## 2. 当前与上一版需求条件

| 条件 | 当前（需求 v2） | 上一版（需求 v1） |
| --- | --- | --- |
| 缓存保留期 | **14 天** | 7 天 |
| SQLite 版本 | **3.46.0** | 3.44.0 |
| 需求版本 | 2 | 1 |
| 负责人 / 上线日期 | 未指定（v2 未提） | 未指定 |

读取引用（页面 + 原文）：

- 当前：Wiki 页 **需求 v2（现行）与变更影响**，记录 **d2b160eab1314f1a8b04ccef97153ff6**，版本 **1**；原文 **015a6d73308148cebaadc0ee7e6ce163**，版本 **1**（`project-change-v2.md`，sha256 7c267717…）。
- 历史：Wiki 页 **需求 v1（历史，已被 v2 取代）**，记录 **6ddbf29274034c7690dcafb732382057**，当前版本 **2**（`status: superseded`）；其版本 **1** 仍可取回，对应原需求原文 **56dea0631a56496f87bb107175c2d201**，版本 **1**（`project-brief.md`，sha256 eeb9cf25…）。
- 引用方式：`kb_fetch(id=6ddbf292…, version=1)` 取历史页原文；`kb_fetch(id=56dea063…)` 取需求原文。

两页均声明需求文件是虚构测试材料，不是 SQLite/USGS 官方声明。

## 3. JSONB 建议与共享目录提议

### 3.1 JSONB 建议必须随版本调整（已调整）

- v1（3.44.0）结论：「不能依赖 JSONB」，`jsonb_*`、`json_pretty()` 不可用。
- v2（3.46.0）结论：**可以依赖 JSONB**。依据：0010（3.45.0，a4c9e46495ff4c15bb9436d590ae9595 v1）JSON 函数改用 JSONB 解析树；0011（3.46.0，3bdc3627becd44de847740bd6f45186f v1）新增 `json_pretty()` 与 `strftime` 的 `%G/%g/%U/%V`；0005（3f96bb93535940a698476d077dadd85e v1）第 3.2 节明确 JSONB 自 3.45.0 起。
- 仍不可用：`jsonb_each()`/`jsonb_tree()`（3.51.0）、`->` 负整数下标（3.47.0），见 0005 第 4.24、4.10 节。
- 知识页落点：SQLite 版本边界页 9efc8dcf889d4bfe9a74bcba6758d279 **版本 3**；FAQ 296bf9f082f841849e9c311e00168f09 **版本 3** 的 Q7。均已在正文中把旧结论标为「已失效」。

结论：建议已随版本调整；若仍按 v1 的「不能用 JSONB」回答，就是错的。

### 3.2 共享目录提议：不可行（仍属待评估，未验证）

- 状态：需求 v2 中的 **待评估提议**，项目未确认，未做实测；知识页中标注为 proposal，未写成已验证结论（requirements-v2 d2b160ea… v1 第 3 节）。
- 依据一：0001 第 2 节（555e87ece9cf4cbf8c91b3d2fc373f9f v1，第 241–290 行）——多机通过网络直接访问同一数据库应改用客户端/服务器引擎；网络文件系统锁实现常有缺陷，两个以上客户端可能同时修改同一区域导致**数据库损坏**，SQLite 无法阻止。
- 依据二：0002 第 1 节（f133872facee49068540e914b83be831 v1，第 10–81 行）——WAL 要求所有进程在同一主机共享内存，「WAL does not work over a network filesystem」；第 2.2 节进一步说明 wal-index 依赖共享内存，故读者必须同机。
- 结论口径：按现有官方文档，该做法缺乏支持且有已知损坏风险，**不建议推进**；如需继续只能作为待验证试验并需项目决策与额外测试。知识库未把该提议升级为已验证方案。

## 4. 知识页更新状态、待核对项与 WAL 原文取回

### 4.1 已更新到新来源的页面（lint 实测 7 页、36 条边、无孤儿/过期/未标注来源）

| 页面 | 记录 ID | 版本 | 状态 |
| --- | --- | --- | --- |
| 需求 v2（现行） | d2b160eab1314f1a8b04ccef97153ff6 | 1 | 新页，引用 015a6d73… |
| 需求 v1（历史） | 6ddbf29274034c7690dcafb732382057 | 2 | 标注 superseded，保留 v1 版本 |
| 总览 | 60cee721f0884a95b9ba474db7f6e077 | 2 | 已改为 v2 / 3.46.0 / 14 天 |
| SQLite 版本边界 | 9efc8dcf889d4bfe9a74bcba6758d279 | 3 | 按 3.46.0 重写 |
| 观测说明 | 2f0d7f3bf2ee4f6da80e80c96eb4a169 | 2 | 481 行、全月、去重经过 |
| 资料与来源 | 2fa441087fe94d909939f8c93c8d282e | 2 | 记录增量批次与重复资料处理 |
| FAQ | 296bf9f082f841849e9c311e00168f09 | 3 | Q6/Q7 版本更新、Q12 改 14 天、新增 Q13/Q14 |

### 4.2 仍需核对（未修改记录）

1. **WAL-reset bug 未在知识页覆盖**：0002 第 11 节说明该缺陷影响 3.7.0（2010-07-21）至 3.51.2（2026-01-09），3.51.3（2026-03-13）修复，并对 3.44.6、3.50.7 提供回移。项目当前 3.46.0 落在受影响区间，且文中未列出 3.46.x 的回移 → 需要项目确认补丁/升级决策。现有版本页与 FAQ 尚未写入这一条。
2. **总览页来源登记不全**：overview（60cee721… v2）正文引用了需求 v2 记录，但其 `sources` 元数据只登记 56dea063… 与 ca209cbd…，未登记 015a6d73… → 需要补登记以保持可追溯（本次只读，未改）。
3. **0005 JSON 页面版本偏高**：页面更新于 2026-07-01，含 3.45/3.46/3.47/3.51 特性，引用时须逐条看「added with version」。
4. **本机 SQLite 实际版本未核实**：3.46.0 是项目声明值；本机构建版本、编译选项（JSON 支持、默认外键）资料未给出，无法核查。
5. **0013 字段定义缺失**：仍只有列名，无单位/取值/定义。
6. **共享目录提议**：仍待项目决策，知识库只给出文档评估。
7. **held_out 与追加的对应关系**：数量吻合（181），但资料未明示逐行同源，无法核查。
8. 需求 v1 的历史页仍保留 3.44.0 表述（按设计），引用时须注意其 `status: superseded`。

### 4.3 WAL 官方资料完整原文：可取回

- 记录：**f133872facee49068540e914b83be831**，版本 **1**，node instance-53334db5dad853ada65a-0。
- 取回结果：全文 31,013 字符、11 个章节（含 2.1 Checkpointing、2.2 Concurrency、3.x 配置、5 只读库、6 避免过大 WAL、9 SQLITE_BUSY、11 WAL-reset bug）完整返回，末行为原文「This page was last updated on 2026-08-25 19:42:39Z」，无截断。
- 出处：`https://www.sqlite.org/wal.html`（final_url 同上），快照 2026-10-15，raw SHA256 `f3467b53…`，归档 `knowledge/intakes/19cf27959f1540a2a540cb85c2f4d36c/original.md`（hash 56689d1a…）。
- 可引用的原句：
  - 「WAL provides more concurrency as readers do not block writers and a writer does not block readers.」（第 1 节）
  - 「since there is only one WAL file, there can only be one writer at a time.」（第 2.2 节）
  - 「All processes using a database must be on the same host computer; WAL does not work over a network filesystem.」（第 1 节）
- 补发文件与此记录同 hash，说明「取回完整原文」与「去重」并不冲突：重复提交不生成新记录，原文仍可取回。

## 5. 无法核查 / 未完成

- 无法核查本机实际 SQLite 版本与编译选项（无本机执行环境权限，资料也未给出）。
- 无法核查导出缓存 14 天的落地实现（需求未描述）。
- 无法核查共享目录提议的实际可行性（未实测，且资料明确不作为已验证结论）。
- 无法核查 181 行追加与初始 held_out 是否逐行同一集合（仅数量一致）。
- 以上均如实记录，未通过修改知识记录来掩盖；如需修正（如补 WAL-reset bug、补登记总览 sources），应在后续写入阶段处理。
