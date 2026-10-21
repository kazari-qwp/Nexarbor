# 客户端重启后持久化核查（只读）

任务：task/ee490f0a32124d3b9f35a778d8d897e0（mode=read）。本次未修改任何知识记录；以下均为重启后实际读取结果。

## 1. 结论

- 重启后 4 个集合全部存在，观测、目录、原文与 Wiki 历史版本均可读取。
- 观测总数仍为 **481**（与重启前一致，无丢失、无重复增长）。
- 现行项目条件：缓存保留 **14 天**，SQLite **3.46.0**（需求 v2）。
- 上一版（v1）要求原文与页面历史版本均可取回：缓存 7 天、SQLite 3.44.0。

## 2. 集合持久化

`kb_catalog` 返回 4 个集合：

| 集合 | ID | 存储 |
| --- | --- | --- |
| earthquake-observations | 485b34c69ca84e0fb2174ba6375d3a12 | sqlite |
| quake-source-docs | f7c4681bd24f45409cbcc69aa86d6445 | rag |
| quakedesk-wiki | 7efeb104ee854e7889bdb60911802638 | wiki |
| reference-catalog | 8f01f5ed5e064888ac485ebd2a9906bc | csv |

## 3. 观测数据核查

- `kb_query(count)`：**481**。
- 按 network：**us 477、ak 2、ci 1、tx 1**。
- 最新 time_utc：**2024-09-30T21:14:17.212Z**（与重启前一致）。
- 说明：数量与分布和重启前（2026-10-20 增量导入后）完全相同，说明追加数据与去重结果已持久化。

## 4. 当前项目条件与依据

- 缓存保留：**14 天**；SQLite：**3.46.0**。
- 依据页：**需求 v2（现行）与变更影响**，记录 **d2b160eab1314f1a8b04ccef97153ff6**，版本 **1**，读取正常（`index_state: ready`）。
- 依据原文：**015a6d73308148cebaadc0ee7e6ce163**，版本 **1**（`project-change-v2.md`，sha256 `7c267717…`）。

## 5. 上一版要求的原文与版本引用

取回结果（两处互相印证）：

1. 上一版需求原文：记录 **56dea0631a56496f87bb107175c2d201**，版本 **1**，内容为 `imports/project-brief.md` 全文，其中明确「当前可用的 SQLite 版本是 3.44.0」「导出缓存保留 7 天」「没有指定项目负责人或承诺上线日期」。归档副本见其 `origins`：`knowledge/intakes/e342215118bf4d24817080747dc5b15f/original.md`，hash `eeb9cf25…`。
2. 上一版知识页：记录 **6ddbf29274034c7690dcafb732382057**，当前版本 **2**（标题「需求 v1（历史，已被 v2 取代）」，`status: superseded`）；`kb_fetch(version=1)` 仍可返回首次发布版本，标题「需求 v1 与约束」，同样写 3.44.0 / 7 天。

引用写法：

- 历史页首版：`kb_fetch(id="6ddbf29274034c7690dcafb732382057", version=1)`
- 历史页现行（带历史标注）：`kb_fetch(id="6ddbf29274034c7690dcafb732382057")`
- 需求 v1 原文：`kb_fetch(id="56dea0631a56496f87bb107175c2d201")`（version 1）
- 现行需求页：`kb_fetch(id="d2b160eab1314f1a8b04ccef97153ff6")`（version 1）

## 6. 其他资料可用性抽查

- RAG 原文：`kb_fetch(id="14445ea2a7b3464fbbf8f42c096638f3")`（0009，3.44.0 发行说明，版本 1）返回完整正文与出处（Source ID/URL/Snapshot/SHA256），状态 ready。
- Wiki 链接解析正常：现行页 → requirements-v1（v2）、sqlite-version（v3）、observations-guide（v2）、sources-and-collections（v2）、overview（v2）、faq（v3），全部 `resolved`，无 needs_refresh。

## 7. 未核查 / 限制

- 本次只做读取，未验证并发写入或重启期间的写入恢复行为。
- 未重新核验本机 SQLite 实际版本（3.46.0 仍是项目声明值，非本机探测结果）。
- 未重新计算全部统计指标（仅取证总数、分组与时间上界），与重启前交付一致。
- 知识库内引用以记录 ID + 版本为准；归档文件路径仅作溯源线索。
