# QuakeDesk 首批资料归档交付（阶段一）

任务：task/9ba6ac388971460eb0cd13702803fdb4（mode=agent）。范围：仅工作区首批 18 个文件；未访问网络、未读取工作区外文件。原始任务见 task/input（sha256 159670ec…）。

## 1. 结论摘要

- 已实际创建 4 个集合，写入 334 条记录（13 篇英文原文 + 1 份来源清单 + 1 份项目说明 + 14 条目录 + 300 条观测 + 6 个 Wiki 页），全部为版本 1 或 2，均可按记录 ID + 版本取回。
- 6 个中文知识页已发布并通过 lint（无孤儿页、无过期来源、无未标注来源页），覆盖需求 v1、来源与集合、观测数据口径、SQLite 3.44.0 版本边界、FAQ。
- 已完成可用性验证：全文取回（45,647 字符的 JSON 文档完整返回）、语义检索命中、CSV 条件筛选、SQLite 计数/分组/极值统计、目录导出 14 行。
- 发现并对知识页做了限定：观测快照只有 300/481 行，覆盖 2024-09-01 至 2024-09-18，不能当作全月数据。

## 2. 集合用途与保存数量

| 集合 | ID | 存储 | 用途 | 数量 |
| --- | --- | --- | --- | --- |
| quake-source-docs | f7c4681bd24f45409cbcc69aa86d6445 | RAG | 英文技术原文、发布日志、来源清单、项目说明；按主题召回段落并可回取全文与出处 | 15 条 |
| reference-catalog | 8f01f5ed5e064888ac485ebd2a9906bc | CSV | 小型固定文献目录，保留 source_id 前导零，可作表格交换 | 14 条 |
| earthquake-observations | 485b34c69ca84e0fb2174ba6375d3a12 | SQLite | 观测记录，按台网/震级/时间筛选统计，持续追加 | 300 条 |
| quakedesk-wiki | 7efeb104ee854e7889bdb60911802638 | Wiki | 项目知识页与 FAQ，可修订并保留历史版本 | 6 页 |

划分理由：技术文档长且需逐段召回 → RAG；目录小、固定、需交换且 source_id 必须保留前导零 → CSV（source_id 声明为 string）；观测持续追加且需条件查询统计 → SQLite；项目解释需中文、互链、可修订 → Wiki。

## 3. 实际存储回执

### 3.1 quake-source-docs（node instance-53334db5dad853ada65a-0，全部 version 1）

| source_id | 记录 ID | 说明 |
| --- | --- | --- |
| 0001 | 555e87ece9cf4cbf8c91b3d2fc373f9f | Appropriate Uses For SQLite |
| 0002 | f133872facee49068540e914b83be831 | Write-Ahead Logging |
| 0003 | b1fa49cb91584e609878f7f2024db08a | Isolation In SQLite |
| 0004 | 3e23bd00e0f641d8a51ad9c11eaf399b | SQLite Foreign Key Support |
| 0005 | 3f96bb93535940a698476d077dadd85e | JSON Functions And Operators |
| 0006 | 07bd0da341194acea85489b426d2d287 | The WITH Clause |
| 0007 | c37097519b4a4ca7a47a699e6a9c6635 | UPSERT |
| 0008 | e8f917e7f87d4f888922a5a837e342e2 | Quirks, Caveats, and Gotchas |
| 0009 | 14445ea2a7b3464fbbf8f42c096638f3 | Release 3.44.0 |
| 0010 | a4c9e46495ff4c15bb9436d590ae9595 | Release 3.45.0 |
| 0011 | 3bdc3627becd44de847740bd6f45186f | Release 3.46.0 |
| 0012 | b47dbc352ffd4d0fb5ab69ce03fe0a49 | USGS Event API |
| 0013 | 0624c065c14e4340876e61538e97d511 | USGS Spreadsheet Format |
| — | ca209cbdbc5c40a8bf2ef184d93416f1 | SOURCES.json 来源清单与快照信息（记录 key 误拼为 sources-manifest-soources-json，内容完整） |
| — | 56dea0631a56496f87bb107175c2d201 | imports/project-brief.md 需求 v1 原文 |

### 3.2 reference-catalog（node instance-411d672032dd23e9d056-0，14 条，version 1）

记录 ID 顺序：70a5d054e7924b358bd265b8d41ddda5、79e46f7fee6a4c2490ca499bee3a20d8、1d76ad1bcb7b4a76adf034c7b1a22fe6、43e18d53dcde4e2886e8d478aee3438d、fd74aad6ee2d49b8a2ad80cca5763b1c、1dffc769dba24c8eb53bdb57b9d976a6、d65966b749bf45b0bab31cfd5249bcf8、f860ba1920cc4fecab4a60f6b4739d16、aa2eaa250e0b4257a5cfcbd07543b20a、9e518bcf4a92451bb925c9c844c7bd44、22377e5e66244cffae3fc722043a2012、54af9d93a41a4c8f83cb43657b05537c、33e58ae83a4641e3a214e73bc43e7345、943f1e6dc9054d83b463f403c1c73727。

### 3.3 earthquake-observations（node instance-db4021b056f586415d9e-0，300 条，version 1）

首条 7459e9fb3c284821bc084e6c8f38c136（us6000nny2），末条 55f9a7bf2bb44213ae5c6cc6766ffb59。原始来源归档 intakes/305bec4848bc4df78f3266a4d81e5e95/original.json，hash 690cb953… 与 SOURCES.json 中 0014 的 sha256 一致。

### 3.4 quakedesk-wiki（node instance-78d9523725ec87628b4e-0）

| 页面 | key | 记录 ID | 版本 |
| --- | --- | --- | --- |
| QuakeDesk 项目知识总览 | overview | 60cee721f0884a95b9ba474db7f6e077 | 1 |
| 需求 v1 与约束 | requirements-v1 | 6ddbf29274034c7690dcafb732382057 | 1 |
| 资料集、来源与检索方式 | sources-and-collections | 2fa441087fe94d909939f8c93c8d282e | 1 |
| 观测数据说明与统计口径 | observations-guide | 2f0d7f3bf2ee4f6da80e80c96eb4a169 | 1 |
| SQLite 版本边界（3.44.0） | sqlite-version | 9efc8dcf889d4bfe9a74bcba6758d279 | 2 |
| 常见问题（12 问） | faq | 296bf9f082f841849e9c311e00168f09 | 2 |

版本 2 的两页是因为校对原文后修正了 JSONB/jsonb_each 的版本归属（3.45.0 / 3.51.0 / 3.47.0），历史版本 1 仍可取回。

### 3.5 导出回执

- kb_export(reference-catalog, csv) → count 14，path `knowledge/exports/c6318590af9747beb9ad9aba45cc66f8.csv`。

## 4. 读取与验证证据（实际调用结果）

1. 全文完整：kb_fetch 3f96bb93…（0005，声明 45,647 字符）返回全部章节直至原文末尾「This page was last updated on 2026-07-01 11:31:04Z」，无截断。
2. 结构化取回：kb_fetch 7459e9fb… 返回完整 JSON 行，origins.hash 690cb953… 与来源清单一致。
3. 统计核验（口径：快照 300 行，2024-09-01 至 2024-09-18，M≥4.5）：count=300；network：us 296、ak 2、ci 1、tx 1；magnitude min 4.5 / max 6.5；avg(depth_km)=58.2093；magnitude_type：mb 229、mww 63、mwr 5、ml 1、mw 1、mwb 1；review_status 全为 reviewed；time_utc 首 2024-09-01T00:49:26.519Z、末 2024-09-18T07:52:28.320Z。
4. 语义检索：kb_search(quake-source-docs, semantic=true, "写事务和读事务的并发与快照隔离") → method=hybrid，命中 0002（2.2/2.3 节）、0001、0003，均带 section_fetch / window_fetch。
5. CSV 条件筛选：kb_search(reference-catalog, filters={source_id:"0014"}) → total 1，source_id 原样 "0014"，前导零保留。
6. Wiki 健康：kb_wiki lint → 6 页、27 条链接边、orphans 空、stale 空、unsourced 空、wantedPages 空；kb_index(quakedesk-wiki) → status ready。

## 5. 知识页要点

- 总览：项目条件表、四集合分工、阅读顺序、使用边界（中文提问、英文原文为准、缺失不补猜）。
- 需求 v1：逐条需求 + 落地映射 + 明确缺失项（负责人、上线日期、编译选项、追加/去重规则、缓存清理机制）。
- 资料与来源：14 条来源表、快照时间 2026-10-15T17:08:53+08:00、快照 300/481 的限定、检索路径。
- 观测数据：字段与 USGS CSV 列名对应、覆盖范围、已验证统计值、解释注意事项。
- 版本边界：3.44.0 可用清单；3.45.0/3.46.0 不可用清单；0005 页面偏新导致的功能误用风险。
- FAQ：选型、UPSERT、WAL 并发、快照隔离与 BEGIN IMMEDIATE、外键默认关闭、时间存储、JSON 版本限制、递归 CTE、前导零、统计口径、负责人/上线缺失、缓存实现缺失。

## 6. 尚未解决的问题

1. 观测快照不完整：481 行仅保留 300 行，覆盖到 09-18；缺 181 行且 09-19 至 09-30 无数据，全月统计不可做，需后续增量补齐。
2. 0013 只列 CSV 列名，未给字段定义/取值/单位；字段语义目前依赖 SOURCES.json 的规范化说明，不是官方定义。
3. 选样说明称「500-event cap」，而 0012 写明服务 limit 上限为 20000；500 应为自设 limit，两者未被原文统一，已在数据页按 0012 解释、未改动原文。
4. 项目层面的缺口：负责人、上线日期、SQLite 编译选项、观测追加频率与去重规则、导出缓存 7 天的实现，资料均未覆盖。
5. 0005 JSON 文档页面更新于 2026-07-01，含 3.45.0/3.46.0/3.47.0/3.51.0 特性，与项目 3.44.0 存在系统性偏差；已在版本页与 FAQ 限定，但任何引用该页回答 3.44.0 问题时仍需逐条核对。
6. SOURCES.json 记录的 key 存在拼写错误（sources-manifest-soources-json）；为保证 Wiki sources 引用不中断，未删除重建，仅记录在此。
7. 未创建助手：本阶段工具集中没有创建助手的接口，需求也只要求归档与知识页维护；问答入口由 Wiki 总览 + FAQ 承担。若后续需要固定问答界面，再单独评估。
8. 未处理后续查询与增量更新：按任务要求留待下一阶段；本次未联网，也未使用 held_out 的 181 行。

## 7. 引用登记

- RAG 原文与来源清单：node instance-53334db5dad853ada65a-0，记录 555e87ec…/f133872f…/b1fa49cb…/3e23bd00…/3f96bb93…/07bd0da3…/c3709751…/e8f917e7…/14445ea2…/a4c9e464…/3bdc3627…/b47dbc35…/0624c065…/ca209cbd…/56dea063…（均 version 1）。
- CSV 目录：node instance-411d672032dd23e9d056-0，14 条 version 1。
- 观测：node instance-db4021b056f586415d9e-0，300 条 version 1。
- Wiki：node instance-78d9523725ec87628b4e-0，6 页（overview/requirements-v1/sources-and-collections/observations-guide 为 v1；sqlite-version/faq 为 v2）。
