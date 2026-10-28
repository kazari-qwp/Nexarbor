增量写入阶段：处理 imports/updates/ 下三份新材料。
1) earthquakes-additional.csv 追加到 quake-events，按 event_id 去重，保留原字段精度与 UTC；
2) project-change-v2.md 为同一项目需求变更：保存为 v2 现行要求，保留 v1 原文与历史来源，并维护依赖的知识页（项目知识页/FAQ/导航），区分「待评估提议」与「已核实技术结论」；
3) duplicate-document.md 为补发资料：核对是否与已有原文重复，重复则关联复用、不重复累计，并保留来源；
完成后再次导入同一份 earthquakes-additional.csv，核查观测数量未增加。
要求实际保存、检索核查、交付引用，不只描述计划。