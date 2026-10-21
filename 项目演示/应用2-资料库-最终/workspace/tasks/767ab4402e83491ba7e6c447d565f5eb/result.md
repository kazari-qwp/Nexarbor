# 增量写入交付：追加观测、需求 v2、重复资料与重复导入核查

任务：task/767ab4402e83491ba7e6c447d565f5eb（mode=write）。范围：`imports/updates/` 三份材料；未联网、未读取工作区外文件。

## 1. 结论摘要

- 追加观测 181 行已并入 `earthquake-observations`：300 → **481 行**，覆盖 2024-09-01 至 2024-09-30，与来源查询窗口匹配数一致。
- 需求变更 v2 已归档并按「现行 v2 / 历史 v1」重构知识页；v1 原文与 v1 页面均保留。
- 补发 `duplicate-document.md` 与 0002 内容完全相同（sha256 一致），**未新建记录**，避免重复累计。
- 重复导入同一 CSV 后，181 行全部复用既有记录（版本递增），集合仍为 **481 行**，未增加。
- 待评估提议（两台计算机共享目录访问同一 SQLite 文件）单独标注为 proposal，与已验证结论分开；未写成已验证方案。

## 2. 追加观测：实际回执

| 项目 | 结果 |
| --- | --- |
| 输入 | `imports/updates/earthquakes-additional.csv`（181 行，sha256 `aa3d1493…`） |
| 首次写入 | intake 08a75660445d4b26b3881c7c7253a0c6 → 记录 2e8dda69e18f472bbd6d1f5cf31291eb（us6000nsv4，v1） |
| 补写其余 | intake 2a61aa4dc0e94bbabee50e6c8dd18645 → 180 条新记录（v1），另 1 条复用 2e8dda69（v2） |
| 追加后计数 | 481 |
| 新增记录示例 | 2e8dda69e18f472bbd6d1f5cf31291eb（us6000nsv4）、09ec36bef45a4a94ae73a5d5c53e5499…11793986e4f1424595552bd5074845e8（共 180 条 v1） |
| 覆盖范围 | 2024-09-01T00:49:26.519Z – 2024-09-30T21:14:17.212Z |
| 震级范围 | 4.5 – 6.5 |
| 台网/状态 | us 477、ak 2、ci 1、tx 1；reviewed 481 |

字段保持原文：event_id、毫秒 UTC 时间、经纬度精度、震级与震级类型。

## 3. 重复导入核查（同一 CSV 第三次提交）

- 输入：同一文件再导入，intake ef694a81994447e4872cdd1561d38696。
- 存储结果：181 条全部映射回既有记录，仅版本号递增 —— 首条 2e8dda69 → **v3**，其余 180 条 → **v2**；`remaining_indices` 为空，无新记录 ID。
- 核查计数：导入前 481，导入后仍 **481**。
- 单条核查：`kb_search(earthquake-observations, "us6000nsv4")` → total **1**，记录 2e8dda69…，version 3。
- 结论：重复提交不会重复累计；版本递增是重复提交的可见痕迹，内容字段未变。

## 4. 需求 v2：归档与知识页重构

- 原文归档：RAG 记录 **015a6d73308148cebaadc0ee7e6ce163**，版本 1，sha256 `7c267717…`。
- 现行页：新增 **需求 v2（现行）与变更影响**，记录 d2b160eab1314f1a8b04ccef97153ff6，版本 1。
- 历史页：需求 v1 页更新为「历史，已被 v2 取代」，记录 6ddbf29274034c7690dcafb732382057，版本 2（v1 版本仍可取回），原文记录 56dea063… 未改动。
- 相关页同步：
  - 总览 60cee721f0884a95b9ba474db7f6e077 → v2（需求版本 2、SQLite 3.46.0、缓存 14 天）。
  - SQLite 版本边界 9efc8dcf889d4bfe9a74bcba6758d279 → v3（按 3.46.0 重写；3.44 时代结论标为失效）。
  - 观测说明 2f0d7f3bf2ee4f6da80e80c96eb4a169 → v2（481 行、全月、去重经过）。
  - 资料与来源 2fa441087fe94d909939f8c93c8d282e → v2（新增批次、重复资料处理记录）。
  - FAQ 296bf9f082f841849e9c311e00168f09 → v3（Q6/Q7 版本更新、Q10 口径 481、Q12 改 14 天、新增 Q13/Q14）。

## 5. 重复资料判定（duplicate-document.md）

- 提交文件 sha256：`56689d1a6a1d2d63a8b34a90576e212bf18afbf9ad692677cb09451d1bf4ae59`。
- 既有 0002 记录 f133872facee49068540e914b83be831 的归档 hash 完全相同；文件头亦标注 `Source ID: 0002`、`Raw SHA256: f3467b53…`。
- 处理：**未写入新记录**。检索验证：`kb_search(quake-source-docs, "Write-Ahead Logging")` 仅返回 SOURCES.json 与 0002 记录，没有第三份副本。
- 引用方式：需要该资料时直接使用 0002 记录（版本 1）。

## 6. 待评估提议 vs 已验证结论

**待评估（proposal，未验证、未确认）**：两台计算机通过共享目录直接访问同一个 SQLite 数据文件。
- 状态：proposal；项目未确认，未实测。
- 文档评估意见：0001 第 2 节指出多机通过网络直接访问同一库应改用客户端/服务器引擎，网络文件系统锁缺陷可能导致数据库损坏；0002 第 1 节指出 WAL 不能用于网络文件系统。结论口径为「缺乏官方支持、存在已知损坏风险，不建议推进」，并说明若继续只能作为待验证试验。
- 未使用「已验证可行」「已采纳」等表述。

**已验证结论（有原文或查询结果）**：
- 3.46.0 可用 JSONB、`json_pretty()`、`strftime()` 的 `%G/%g/%U/%V`（0010/0011）；`jsonb_each/jsonb_tree`（3.51.0）与 `->` 负下标（3.47.0）仍不可用（0005）。
- 观测集合 481 行、去重与重复导入行为（本次实际查询）。
- WAL 读写并行、单写者、不能跨机网络文件系统（0002）。
- 外键默认关闭（0004/0008）。

## 7. 检索与健康核查

- `kb_query` count：481；network：us 477/ak 2/ci 1/tx 1；magnitude_type：mb 364/mww 104/mwr 10/ml 1/mw 1/mwb 1；avg(depth_km)=61.09；reviewed 481；max(time_utc)=2024-09-30T21:14:17.212Z。
- `kb_search(quake-source-docs,"Write-Ahead Logging")`：total 2（来源清单 + 0002），无重复副本。
- `kb_search(quakedesk-wiki, semantic=true,"现行 SQLite 版本 3.46.0 导出缓存 14 天")`：method=hybrid，命中 FAQ v3、总览 v2、需求 v1 历史页（含 v2 说明段）。
- `kb_wiki lint`：7 页、36 条边、orphans/stale/unsourced/wantedPages 均为空。
- `kb_index(quakedesk-wiki)`：status ready。

## 8. 尚未解决 / 需注意

1. 需求 v2 声明的 3.46.0 是项目口径；本机实际构建版本与编译选项（是否含 JSON、默认外键）未在资料中给出，落地前需用 `sqlite_version()` 等核对。
2. 共享目录提议仍待项目决策；知识库只给出文档评估，不构成验证。
3. 重复导入使 181 条记录的 `metadata.purpose` 被最后一次提交的描述覆盖，且版本升至 2/3；内容未变，但若需要更细的提交溯源，应改用按 event_id 的 UPSERT 或保留独立导入日志。
4. 0013 仍只列 CSV 列名，无字段定义；`place` 为英文、`network` 代码含义未在资料中定义。
5. 导出缓存 14 天的存放位置、清理机制、失败处理仍未说明；负责人与上线日期仍未指定。
6. 初始快照的 `held_out_rows=181` 与本次追加 181 行数量吻合，但资料未明示二者为同一补集；本页按「合计等于 481 匹配数」表述，未断言逐行同源。

## 9. 引用登记

- 追加批次 CSV 归档：intakes/08a75660445d4b26b3881c7c7253a0c6/original.csv（sha256 aa3d1493…）；重复提交 intakes/ef694a81994447e4872cdd1561d38696。
- 需求 v2：RAG 015a6d73308148cebaadc0ee7e6ce163 v1；需求 v1：56dea0631a56496f87bb107175c2d201 v1。
- 重复资料：与 0002 记录 f133872facee49068540e914b83be831 v1 同 hash，未新增。
- 观测记录样例：2e8dda69e18f472bbd6d1f5cf31291eb v3（us6000nsv4）；7459e9fb3c284821bc084e6c8f38c136 v1（us6000nny2）。
- Wiki：requirements-v2 d2b160ea… v1；requirements-v1 6ddbf292… v2；overview 60cee721… v2；sqlite-version 9efc8dcf… v3；observations-guide 2f0d7f3b… v2；sources-and-collections 2fa44108… v2；faq 296bf9f0… v3。
