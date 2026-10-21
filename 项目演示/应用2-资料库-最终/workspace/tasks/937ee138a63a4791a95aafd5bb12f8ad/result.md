# 阶段二只读查询交付：6 个问题的回答与依据

任务：task/937ee138a63a4791a95aafd5bb12f8ad（mode=read）。本次只读，未新增、修改或删除任何知识记录；所有数字与条目来自知识库实际读取结果。详细依据保留在本文件，结论按问题编号给出。

## 1. 观测总数、分组计数与范围

数据集合：`earthquake-observations`（collection 485b34c69ca84e0fb2174ba6375d3a12，node instance-db4021b056f586415d9e-0）。

- 总数：**300**。
- 按 network：**us 296、ak 2、ci 1、tx 1**。
- 按 review_status：**reviewed 300**（无其他状态）。
- 时间范围（time_utc，ISO8601 UTC 文本）：**2024-09-01T00:49:26.519Z 至 2024-09-18T07:52:28.320Z**。
- 震级范围：**4.5 至 6.5**。

口径说明（必读）：这是快照的实际范围。原始查询窗口是 2024-09-01 至 2024-10-01、M≥4.5、按时间升序，该窗口共匹配 481 行，快照只保留 300 行（181 行未包含，`held_out_rows`），因此末条时间为 09-18 而不是 09-30（依据：SOURCES.json 记录 ca209cbdbc5c40a8bf2ef184d93416f1 版本 1）。因此上述计数与范围只能表述为「快照 300 行（2024-09-01 至 2024-09-18，M≥4.5）」。

## 2. 最大震级与完整记录

- 最大震级：**6.5**。
- 对应 event_id：**us7000ne51**（该震级仅 1 条）。
- 记录 ID：**f90c4481c5fd4c3e9a21316c6ed0eeae**，版本 **1**（node instance-db4021b056f586415d9e-0）。
- 完整原始字段（kb_fetch 返回，未改写）：

```json
{
  "depth_km": 3.766,
  "event_id": "us7000ne51",
  "latitude": 51.6088,
  "longitude": -130.6121,
  "magnitude": 6.5,
  "magnitude_type": "mww",
  "network": "us",
  "place": "271 km WNW of Port McNeill, Canada",
  "review_status": "reviewed",
  "time_utc": "2024-09-15T22:22:48.018Z",
  "updated_utc": "2024-11-21T22:58:58.040Z"
}
```

来源归档：`knowledge/intakes/305bec4848bc4df78f3266a4d81e5e95/original.json`，hash `690cb953c4416df290bafc20b09e228b18760be19d0808806913584acc851ca0`，与 SOURCES.json 中 0014 的 sha256 一致。

## 3. 文献目录 0001、0013 的完整条目

集合：`reference-catalog`（collection 8f01f5ed5e064888ac485ebd2a9906bc）。

**0001**（记录 70a5d054e7924b358bd265b8d41ddda5，版本 1）：

```json
{
  "file_path": "imports/documents/0001-sqlite-appropriate-uses.md",
  "snapshot_date": "2026-10-15",
  "source_id": "0001",
  "title": "Appropriate Uses For SQLite",
  "topic": "sqlite",
  "url": "https://www.sqlite.org/whentouse.html"
}
```

**0013**（记录 33e58ae83a4641e3a214e73bc43e7345，版本 1）：

```json
{
  "file_path": "imports/documents/0013-usgs-csv-fields.md",
  "snapshot_date": "2026-10-15",
  "source_id": "0013",
  "title": "Spreadsheet Format",
  "topic": "earthquake",
  "url": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/csv.php"
}
```

两条的 `source_id` 都是字符串，前导零保留。

## 4. WAL 的并发与共享目录问题

依据：0002《Write-Ahead Logging》（记录 f133872facee49068540e914b83be831，版本 1）。

- **读写可并行**：可以。第 1 节原文：“WAL provides more concurrency as readers do not block writers and a writer does not block readers. Reading and writing can proceed concurrently.”（第 10–81 行）
- **多个写者同时写**：不可以。第 2.2 节原文：“Writers merely append new content to the end of the WAL file. Because writers do nothing that would interfere with the actions of readers, writers and readers can run at the same time. However, since there is only one WAL file, there can only be one writer at a time.”（第 124–176 行）
- **两台计算机共享目录上使用**：不可以。第 1 节列为 WAL 的缺点：“All processes using a database must be on the same host computer; WAL does not work over a network filesystem. This is because WAL requires all processes to share a small amount of memory and processes on separate host machines obviously cannot share memory with each other.”（第 10–81 行）
- 补充同向证据：0001 第 2 节（记录 555e87ece9cf4cbf8c91b3d2fc373f9f，版本 1，第 241–290 行）建议避免「同一数据库被多台计算机通过网络直接访问」，并指出网络文件系统的文件锁实现常有缺陷、可能导致损坏。

结论：QuakeDesk 单机场景可用 WAL 获得读写并行，但写入仍需单写者串行；不得把数据库放在两台机器共享的网络目录上。

## 5. 项目当前版本能否依赖 JSONB

**不能。** 项目 SQLite 版本为 3.44.0（需求 v1），而 JSONB 是 3.45.0 引入的能力。

依据链：

1. 技术文档 0005《JSON Functions And Operators》（记录 3f96bb93535940a698476d077dadd85e，版本 1）第 3.2 节原文：“Beginning with version 3.45.0 (2024-01-15), SQLite allows its internal "parse tree" representation of JSON to be stored on disk, as a BLOB, in a format that we call "JSONB".”（第 133–152 行）
2. 发行说明 0010（3.45.0，记录 a4c9e46495ff4c15bb9436d590ae9595，版本 1）：“All JSON functions are rewritten to use a new internal parse tree format called JSONB… New versions of JSON-generating functions generate binary JSONB instead of JSON text.”
3. 发行说明 0011（3.46.0，记录 3bdc3627becd44de847740bd6f45186f，版本 1）新增 `json_pretty()`；0005 第 4.17 节亦注明“The json_pretty() function was added with SQLite version 3.46.0”。
4. 0005 第 4.24 节注明 `jsonb_each()` / `jsonb_tree()` 自 3.51.0（2025-11-04）起提供；`->` 的负数下标自 3.47.0 起。均晚于项目版本。
5. 3.44.0 发行说明（0009，记录 14445ea2a7b3464fbbf8f42c096638f3，版本 1）没有任何 JSONB 相关条目，其新增项为聚合函数 ORDER BY、`concat()`/`concat_ws()`、`string_agg()`、`strftime()` 新转换符等。

在 3.44.0 上可依赖的是传统文本 JSON 能力：`json_*` 标量函数、`->` / `->>`、`json_each` / `json_tree`；`jsonb_*`、`json_pretty()` 不可用。另外 0005 页面更新于 2026-07-01，明显新于项目版本，引用时需按上述版本边界逐条核对。

## 6. 导出缓存、部署位置与组织信息

依据：需求原文 56dea0631a56496f87bb107175c2d201（版本 1，`imports/project-brief.md`）。

- 导出缓存保留：**7 天**（原文「导出缓存保留 7 天」）。
- 部署位置：**一台计算机（本机）**，观测资料和数据文件都保存在本机（原文「部署在一台计算机上，观测资料和数据文件都保存在本机」）。
- 项目负责人：**未指定**（原文「没有指定项目负责人或承诺上线日期」）。
- 承诺上线日期：**未承诺**（同上）。
- 补充缺失说明：导出缓存的具体存放位置、清理机制、失败处理，需求与首批资料均未说明；不能从技术文档推断。

## 附：本次读取清单（记录 ID + 版本 + 位置）

| 用途 | 记录 ID | 版本 | 位置/读取方式 |
| --- | --- | --- | --- |
| 观测统计 | — | — | kb_query，collection earthquake-observations |
| 最大震级完整记录 | f90c4481c5fd4c3e9a21316c6ed0eeae | 1 | kb_fetch 全文 |
| 目录 0001 | 70a5d054e7924b358bd265b8d41ddda5 | 1 | kb_fetch 全文 |
| 目录 0013 | 33e58ae83a4641e3a214e73bc43e7345 | 1 | kb_fetch 全文 |
| WAL 依据 | f133872facee49068540e914b83be831 | 1 | 第 1 节、第 2.2 节 |
| 网络共享补充 | 555e87ece9cf4cbf8c91b3d2fc373f9f | 1 | 第 2 节（241–290 行） |
| JSONB 文档 | 3f96bb93535940a698476d077dadd85e | 1 | 3.2 节、4.17 节、4.24 节 |
| 3.45.0 发行说明 | a4c9e46495ff4c15bb9436d590ae9595 | 1 | JSON 条目 |
| 3.46.0 发行说明 | 3bdc3627becd44de847740bd6f45186f | 1 | json_pretty 条目 |
| 3.44.0 发行说明 | 14445ea2a7b3464fbbf8f42c096638f3 | 1 | 全文新增项 |
| 快照口径 | ca209cbdbc5c40a8bf2ef184d93416f1 | 1 | 0014 条目 rows/held_out_rows/selection |
| 项目条件 | 56dea0631a56496f87bb107175c2d201 | 1 | 当前条件段 |
